"""HTTP endpoints. P4.1 holds the health router only; the session, message and SSE endpoints come with their phases
and follow
`contracts/openapi/agent-service.yaml`."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from fastapi import APIRouter, Response, status

from src.llm.provider import LLMHealth


class ReadinessCheck(Protocol):
    """A dependency whose absence makes the service not ready (P4.2 adds the database)."""

    name: str

    def is_ready(self) -> bool: ...


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
