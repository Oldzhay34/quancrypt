from __future__ import annotations

import hmac

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from quancrypt_data.api.problems import problem

# D-295a: a request body above this is refused before it is parsed (500 events of any schema fit well below it).
MAX_BODY_BYTES = 8 * 1024 * 1024
_TOO_LARGE = "body: larger than 8 MiB"


class GateMiddleware:
    """Pure ASGI, before anything reads the body: `/api/v1/*` needs the internal token (constant-time comparison,
    guardrails-security section 6) and a body of at most `MAX_BODY_BYTES`; a missing length is counted while reading."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1"):
            await self._app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}
        supplied = headers.get("x-internal-token", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), self._token):
            await problem(401, "unauthorized", "Unauthorized")(scope, receive, send)
            return
        length = headers.get("content-length")
        if length is not None and (not (length.isascii() and length.isdigit()) or int(length) > MAX_BODY_BYTES):
            await problem(400, "validation-failed", "Bad Request", _TOO_LARGE)(scope, receive, send)
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
                await problem(400, "validation-failed", "Bad Request", _TOO_LARGE)(scope, receive, send)
                return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self._app(scope, replay, send)
