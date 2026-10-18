"""FastAPI application and lifecycle. Run: `uvicorn src.app.main:app`."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from src.app.api import build_health_router, install_api
from src.app.container import Container, build_container, build_redactor
from src.app.logging_setup import configure_logging, trace_id_var
from src.app.settings import AppSettings, load_settings

_LOG = logging.getLogger("src.app")
# Only a 32-digit hexadecimal id is accepted from a client (it is stored in the audit trail, so free text must not
# get in); any other value is replaced by a generated one (D-232c).
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_QUIET_PATHS = ("/health/liveness", "/health/readiness")


def create_app(settings: AppSettings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.logging, build_redactor(settings))
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Migrations first: a failed migration raises here and the service does not start.
        try:
            container.startup()
            container.start_background()
            _LOG.info("agent-service started (llm provider: %s)", settings.models.llm.provider)
            yield
        finally:
            container.close()
            _LOG.info("agent-service stopped")

    # No interactive docs or schema endpoint: the contract is contracts/openapi/agent-service.yaml.
    app = FastAPI(
        title="Quancrypt agent-service",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        # FastAPI 0.142 ships OpenTelemetry hooks that read OTEL_* variables at startup; nothing may leave the machine
        # (guardrails-security section 1), so they are off even if an exporter package arrives later.
        telemetry={"auto_configure": False, "tracing": False, "metrics": False, "logs": False},
    )
    app.state.container = container
    app.include_router(build_health_router(container.llm_health, checks=container.readiness_checks))
    session = settings.agents.session
    install_api(
        app,
        container.orchestrator,
        session.token.get_secret_value(),
        session.ui_origins,
        settings.agents.guardrails.max_request_chars,
    )

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
