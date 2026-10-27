"""The HTTP application of ingest-api (contracts/openapi/ingest-api.yaml): one command, the health endpoints."""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from quancrypt_data.api.gate import GateMiddleware
from quancrypt_data.api.health import ReadinessCheck, build_health_router
from quancrypt_data.api.problems import problem
from quancrypt_data.facade.ingest_facade import BadRequestError, IngestFacade
from quancrypt_data.trace import trace_id_var

_LOG = logging.getLogger("quancrypt_data.api")
# Only a 32-digit hexadecimal id is accepted from a client; any other value is replaced by a generated one.
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_QUIET_PATHS = ("/health/liveness", "/health/readiness")


def _reject_constant(_: str) -> object:
    raise ValueError("NaN and Infinity are not JSON")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("number out of range")
    return value


def _parse(body: bytes) -> object:
    return json.loads(body, parse_constant=_reject_constant, parse_float=_finite_float)


_PROBLEM_CODES = {404: "not-found", 405: "method-not-allowed"}

# At most this many batches are worked on at once (each 8 MiB body is about 260 MB once parsed; D-297d). The limit is
# enforced here, after the token check, so unauthenticated half-open connections cannot use it up; a further batch
# gets 503.
MAX_CONCURRENT_BATCHES = 4


def create_app(
    facade: IngestFacade,
    *,
    token: str,
    checks: Sequence[ReadinessCheck],
    on_startup: Callable[[], None] = lambda: None,
    on_shutdown: Callable[[], None] = lambda: None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Migrations first: a failed migration raises here and the service does not start. The cause is logged as its
        # class
        # name only: the framework would otherwise log the whole traceback, which can carry connection details.
        try:
            on_startup()
        except Exception as exc:
            _LOG.error("ingest-api could not start (%s)", type(exc).__name__)
            on_shutdown()
            raise RuntimeError("ingest-api could not start") from None
        try:
            _LOG.info("ingest-api started")
            yield
        finally:
            on_shutdown()
            _LOG.info("ingest-api stopped")

    # No interactive docs or schema endpoint: the contract is contracts/openapi/ingest-api.yaml. FastAPI's OpenTelemetry
    # hooks read OTEL_* variables at startup; nothing may leave the machine (guardrails-security section 1): off.
    app = FastAPI(
        title="Quancrypt ingest-api",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        telemetry={"auto_configure": False, "tracing": False, "metrics": False, "logs": False},
    )
    app.include_router(build_health_router(checks))
    app.add_middleware(GateMiddleware, token=token)
    slots = threading.BoundedSemaphore(MAX_CONCURRENT_BATCHES)

    @app.post("/api/v1/events")
    async def ingest_events(request: Request) -> Response:
        if not slots.acquire(blocking=False):
            return problem(503, "overloaded", "Service Unavailable", "too many batches in flight; send it again")
        try:
            return await _ingest(request)
        finally:
            slots.release()

    async def _ingest(request: Request) -> Response:
        try:
            # Parsing 8 MiB takes a third of a second of CPU: off the event loop, so the health endpoints keep
            # answering.
            items = await run_in_threadpool(_parse, await request.body())
        except (ValueError, RecursionError):
            return problem(400, "validation-failed", "Bad Request", "body: not valid JSON")
        if not isinstance(items, list):
            return problem(400, "validation-failed", "Bad Request", "body: not a JSON array")
        try:
            result = await run_in_threadpool(facade.ingest, items)
        except BadRequestError as exc:
            return problem(400, "validation-failed", "Bad Request", f"body: {exc}")
        except Exception as exc:
            # The class name only: a message can carry record data. Nothing was written (one transaction): the sender
            # retries.
            _LOG.error("ingest failed (%s)", type(exc).__name__)
            return problem(500, "internal-error", "Internal Server Error")
        return JSONResponse(
            {
                "received": result.received,
                "accepted": result.accepted,
                "duplicate": result.duplicate,
                "quarantined": result.quarantined,
                "consent_revoked": result.consent_revoked,
                "superseded": result.superseded,
            }
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(_: Request, exc: StarletteHTTPException) -> Response:
        # Unknown paths and methods answer with an RFC 9457 problem too (hexagonal-service section 5).
        return problem(exc.status_code, _PROBLEM_CODES.get(exc.status_code, "internal-error"), "Request refused")

    @app.middleware("http")
    async def trace_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        supplied = request.headers.get("X-Trace-Id", "")
        value = supplied if _TRACE_ID.fullmatch(supplied) else uuid.uuid4().hex
        context = trace_id_var.set(value)
        try:
            response = await call_next(request)
            # Method and status only: the path and the body are not logged.
            level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
            _LOG.log(level, "%s %d", request.method, response.status_code)
        finally:
            trace_id_var.reset(context)
        response.headers["X-Trace-Id"] = value
        return response

    return app
