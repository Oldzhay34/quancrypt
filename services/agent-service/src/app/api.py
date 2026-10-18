"""HTTP endpoints (contracts/openapi/agent-service.yaml): health, sessions, messages (SSE), initial scan (SSE),
clarifications and stop.

Every endpoint but health needs `Authorization: Bearer <QUANCRYPT_SESSION_TOKEN>` (constant-time comparison,
guardrails-security section 6); CORS admits only the UI origins. Errors are RFC 9457 problems with the contract's codes.
The trace id comes from the middleware (`trace_id_var`) and goes on to every downstream call. Request bodies are
checked here (pydantic is allowed in the app layer only); a malformed session id is `not-found`, as the contract says.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal, Protocol
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.app.logging_setup import trace_id_var
from src.llm.provider import LLMHealth
from src.memory.short_term import (
    IdempotencyConflictError,
    IdempotencyKey,
    InvalidRecordError,
    SessionNotFoundError,
)
from src.workflows.orchestrator import (
    EventStream,
    Orchestrator,
    ProjectNotFoundError,
    SessionBusyError,
    UpstreamUnavailableError,
)

_LOG = logging.getLogger("src.app")

PROBLEM_BASE = "https://quancrypt.local/problems/"
# A request body above this is refused before it is parsed (security review P4.6 #2; analyzer D-205c analogue).
MAX_BODY_BYTES = 64 * 1024
# The contract's `Root` pattern, character for character (the contract test compares them); the first three ranges
# are escape text there (YAML cannot hold control characters) and `re` reads them the same way.
ROOT_PATTERN = "^/(workspace|corpus)(/(?!\\.\\.?(/|$))[^/\\u0000-\\u001f\\u007f-\\u009f­؜᠎​-‏ -‮⁠-⁯﻿￹-￻\\\\]+)*$"
_ROOT = re.compile(ROOT_PATTERN)
QUESTION_CODES = Literal[
    "TLS_TERMINATION",
    "JDK_UPGRADE_POSSIBLE",
    "HYBRID_INCAPABLE_PARTNERS",
    "COMPLIANCE_REQUIREMENT",
    "DEVICE_HARDWARE_OPENSSL",
]


class ReadinessCheck(Protocol):
    """A dependency whose absence makes the service not ready (P4.2 adds the database)."""

    name: str

    def is_ready(self) -> bool: ...


class ApiProblem(Exception):
    def __init__(self, status_code: int, code: str, title: str, detail: str | None = None) -> None:
        super().__init__(title)
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail


def problem(status_code: int, code: str, title: str, detail: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"type": PROBLEM_BASE + code, "title": title, "status": status_code}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json")


# ---- request bodies (the contract's schemas) ----


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class CreateSessionBody(_Body):
    project_id: UUID
    language: Literal["tr", "en"] = "tr"


class SendMessageBody(_Body):
    content: str = Field(min_length=1)


class InitialScanBody(_Body):
    root: str = Field(max_length=1024)


class AnswerBody(_Body):
    question_code: QUESTION_CODES
    option_code: str | None = Field(default=None, max_length=32)
    free_text: str | None = Field(default=None, max_length=500)


class AnswerClarificationsBody(_Body):
    answers: list[AnswerBody] = Field(min_length=1, max_length=5)


# ---- health ----


def build_health_router(llm_health: LLMHealth, checks: Sequence[ReadinessCheck]) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health/liveness")
    def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @router.get("/health/readiness")
    def readiness(response: Response) -> dict[str, object]:
        # The LLM never decides readiness (NFR-05): without it the service runs in degraded or LLM-less mode.
        llm = llm_health.status()
        failed = [check.name for check in checks if not check.is_ready()]
        if failed:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "failed": failed, "llm": llm}
        return {"status": "ready", "llm": llm}

    return router


# ---- the API ----


class GateMiddleware:
    """Pure ASGI, before anything reads the body (security review P4.6 #2): `/api/v1/*` needs the bearer token
    (constant-time) and a body of at most `MAX_BODY_BYTES`; a missing length is counted while reading."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1") or scope["method"] == "OPTIONS":
            await self._app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}
        scheme, _, token = headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip().encode("utf-8"), self._token):
            await problem(401, "unauthorized", "Unauthorized")(scope, receive, send)
            return
        length = headers.get("content-length")
        if length is not None and (not (length.isascii() and length.isdigit()) or int(length) > MAX_BODY_BYTES):
            await problem(400, "validation-failed", "Bad Request", "body: larger than 64 KiB")(scope, receive, send)
            return
        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            body.extend(message.get("body", b""))
            more = message.get("more_body", False)
            if len(body) > MAX_BODY_BYTES:
                await problem(400, "validation-failed", "Bad Request", "body: larger than 64 KiB")(scope, receive, send)
                return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self._app(scope, replay, send)


def install_api(
    app: FastAPI, orchestrator: Orchestrator, session_token: str, ui_origins: Sequence[str], max_message_chars: int
) -> None:
    # Order: the gate runs inside CORS (so a 401 still carries the CORS headers) and before routing parses a body.
    app.add_middleware(GateMiddleware, token=session_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ui_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Trace-Id"],
        expose_headers=["X-Trace-Id"],
        allow_credentials=False,
    )
    _install_handlers(app)
    expected = session_token.encode("utf-8")

    def authorize(authorization: str | None = Header(default=None)) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip().encode("utf-8"), expected):
            raise ApiProblem(401, "unauthorized", "Unauthorized")

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize)])

    @router.post("/sessions", status_code=201)
    def create_session(
        request_body: dict[str, Any], idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
    ) -> dict[str, Any]:
        body = _parse(CreateSessionBody, request_body)
        idempotency = None
        if idempotency_key is not None:
            digest = hashlib.sha256(
                ("POST /api/v1/sessions " + json.dumps(request_body, sort_keys=True, separators=(",", ":"))).encode()
            ).hexdigest()
            idempotency = _idempotency(idempotency_key, digest)
        created = orchestrator.create_session(body.project_id, body.language, idempotency, trace_id_var.get())
        session = created.session
        return {
            "id": str(session.id),
            "project_id": str(session.project_id),
            "language": session.language,
            "created_at": session.created_at.isoformat().replace("+00:00", "Z"),
        }

    @router.delete("/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str) -> Response:
        orchestrator.delete_session(_session_id(session_id))
        return Response(status_code=204)

    @router.get("/sessions/{session_id}/messages")
    def list_messages(
        session_id: str, page: int = Query(default=0, ge=0), size: int = Query(default=50, ge=1, le=200)
    ) -> dict[str, Any]:
        result = orchestrator.list_messages(_session_id(session_id), page, size)
        return {
            "items": [
                {
                    "id": str(message.id),
                    "role": message.role.lower(),
                    "content": message.content,
                    "evidence": [
                        {
                            "kind": item.kind.lower(),
                            "reference": item.reference,
                            "source_version": item.source_version,
                        }
                        for item in message.evidence
                    ],
                    "created_at": message.created_at.isoformat().replace("+00:00", "Z"),
                }
                for message in result.items
            ],
            "page": result.page,
            "size": result.size,
            "total": result.total,
        }

    @router.post("/sessions/{session_id}/messages")
    def send_message(session_id: str, request_body: dict[str, Any]) -> StreamingResponse:
        identifier = _session_id(session_id)
        body = _parse(SendMessageBody, request_body)
        if len(body.content) > max_message_chars:  # the scope keeper's limit (D-242a), before anything is stored
            raise ApiProblem(400, "validation-failed", "Bad Request", "content: too long")
        return _sse(orchestrator.begin_message(identifier, body.content, trace_id_var.get()))

    @router.post("/sessions/{session_id}/initial-scan")
    def initial_scan(session_id: str, request_body: dict[str, Any]) -> StreamingResponse:
        identifier = _session_id(session_id)
        body = _parse(InitialScanBody, request_body)
        if not _ROOT.fullmatch(body.root):
            raise ApiProblem(400, "validation-failed", "Bad Request", "root: does not match the analysis root rule")
        return _sse(orchestrator.begin_initial_scan(identifier, body.root, trace_id_var.get()))

    @router.get("/sessions/{session_id}/clarifications")
    def list_clarifications(session_id: str) -> dict[str, Any]:
        return {"items": orchestrator.list_clarifications(_session_id(session_id), trace_id_var.get())}

    @router.post("/sessions/{session_id}/clarifications")
    def answer_clarifications(
        session_id: str,
        request_body: dict[str, Any],
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        identifier = _session_id(session_id)
        body = _parse(AnswerClarificationsBody, request_body)
        if idempotency_key is not None and not 0 < len(idempotency_key.strip()) <= 128:
            raise ApiProblem(400, "validation-failed", "Bad Request", "Idempotency-Key: 1 to 128 characters")
        answers = [answer.model_dump() for answer in body.answers]
        return {"items": orchestrator.answer_clarifications(identifier, answers, trace_id_var.get())}

    @router.post("/sessions/{session_id}/stop", status_code=204)
    def stop(session_id: str) -> Response:
        orchestrator.stop(_session_id(session_id))
        return Response(status_code=204)

    app.include_router(router)


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def api_problem(_: Request, exc: ApiProblem) -> JSONResponse:
        return problem(exc.status_code, exc.code, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(400, "validation-failed", "Bad Request", _violations(exc.errors()))

    @app.exception_handler(SessionNotFoundError)
    async def not_found(_: Request, __: SessionNotFoundError) -> JSONResponse:
        return problem(404, "not-found", "Not Found")

    @app.exception_handler(SessionBusyError)
    async def busy(_: Request, __: SessionBusyError) -> JSONResponse:
        return problem(409, "session-busy", "Conflict", "the session is answering another request")

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict(_: Request, __: IdempotencyConflictError) -> JSONResponse:
        return problem(409, "idempotency-conflict", "Conflict")

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_: Request, __: ProjectNotFoundError) -> JSONResponse:
        return problem(400, "validation-failed", "Bad Request", "project_id: no such project")

    @app.exception_handler(UpstreamUnavailableError)
    async def upstream(_: Request, __: UpstreamUnavailableError) -> JSONResponse:
        return problem(503, "upstream-unavailable", "Service Unavailable")

    @app.exception_handler(InvalidRecordError)
    async def invalid_record(_: Request, __: InvalidRecordError) -> JSONResponse:
        return problem(400, "validation-failed", "Bad Request")

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        _LOG.error("unexpected error (%s)", type(exc).__name__)
        return problem(500, "internal-error", "Internal Server Error")


def _parse[M: BaseModel](model: type[M], body: dict[str, Any]) -> M:
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise ApiProblem(400, "validation-failed", "Bad Request", _violations(exc.errors())) from None


def _violations(errors: Sequence[Any]) -> str:
    """Field paths and reasons only; the rejected values never come back (they can be chat text)."""
    parts = []
    for error in list(errors)[:5]:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        parts.append(f"{location or 'body'}: {error.get('type', 'invalid')}")
    return "; ".join(parts)


def _session_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise SessionNotFoundError("the session does not exist") from None


def _idempotency(key: str, digest: str) -> IdempotencyKey:
    try:
        return IdempotencyKey(key, digest)
    except InvalidRecordError:
        raise ApiProblem(400, "validation-failed", "Bad Request", "Idempotency-Key: 1 to 128 characters") from None


# The longest a waiting SSE response holds a worker thread before it can notice a cancellation.
SSE_POLL_S = 1.0


class _SseResponse(StreamingResponse):
    """Listens for the client's disconnect whatever the server's ASGI spec version (security review P4.6).

    Starlette 1.8 listens only below spec 2.4; otherwise it notices a disconnect when it next sends, which for an answer
    still being worked on is after the run ends. `request.is_disconnected()` does not help either: behind the
    trace-id middleware (`BaseHTTPMiddleware`) its pre-cancelled receive loses the message. On a disconnect the stream
    is cancelled, so `frames` stops polling within `SSE_POLL_S` and its `finally` cancels the run.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with anyio.create_task_group() as group:

            async def stream() -> None:
                with contextlib.suppress(OSError):  # the client is gone (ASGI 2.4 servers raise on send)
                    await self.stream_response(send)
                group.cancel_scope.cancel()

            group.start_soon(stream)
            await self.listen_for_disconnect(receive)
            group.cancel_scope.cancel()


def _sse(stream: EventStream) -> StreamingResponse:
    async def frames() -> AsyncIterator[bytes]:
        try:
            while True:
                ended, event = await run_in_threadpool(stream.poll, SSE_POLL_S)
                if ended:
                    return
                if event is not None:
                    yield f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n".encode()
        finally:
            stream.cancel()  # a still-running answer stops at its next node boundary (no-op once it has ended)

    return _SseResponse(frames(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
