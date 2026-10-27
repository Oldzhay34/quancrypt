"""The ASGI entry point: `uvicorn quancrypt_data.api.ingest:app`. Bootstrap only (like <Servis>Application.java): the
composition root builds the application from the environment; a configuration error stops the process at import time
(fail-fast)."""

from __future__ import annotations

from quancrypt_data.infrastructure.container import build_application

app = build_application()
