"""FastAPI application and lifecycle. Run: `uvicorn src.app.main:app`."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from src.app.api import build_health_router
from src.app.container import build_container
from src.app.logging_setup import configure_logging, trace_id_var
from src.app.settings import AppSettings, load_settings

_LOG = logging.getLogger("src.app")
_TRACE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_QUIET_PATHS = ("/health/liveness", "/health/readiness")


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.logging)
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        _LOG.info("agent-service started (llm provider: %s)", settings.models.llm.provider)
        yield
        container.close()
        _LOG.info("agent-service stopped")

    # No interactive docs or schema endpoint: the contract is contracts/openapi/agent-service.yaml.
    app = FastAPI(
        title="Quancrypt agent-service",
        version="1.0.0-draft",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        # FastAPI 0.142 ships OpenTelemetry hooks that read OTEL_* variables at startup; nothing may leave the machine
        # (guardrails-security section 1), so they are off even if an exporter package arrives later.
        telemetry={"auto_configure": False, "tracing": False, "metrics": False, "logs": False},
    )
    app.state.container = container
    # TODO(P4.1-2): readiness has no dependency check yet; P4.2 adds the database to `checks`
    # (readiness falls only when the database is down).
    app.include_router(build_health_router(container.llm_health, checks=()))

    @app.middleware("http")
    async def trace_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        supplied = request.headers.get("X-Trace-Id", "")
        value = supplied if _TRACE_ID.fullmatch(supplied) else uuid.uuid4().hex
        token = trace_id_var.set(value)
        try:
            response = await call_next(request)
            # Method and status only: the path and the query are not logged (they can carry project data).
            level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
            _LOG.log(level, "%s %d", request.method, response.status_code)
        finally:
            trace_id_var.reset(token)
        response.headers["X-Trace-Id"] = value
        return response

    return app


app = create_app()
