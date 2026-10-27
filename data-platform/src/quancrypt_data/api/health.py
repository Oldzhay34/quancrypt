from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from fastapi import APIRouter, Response, status


class ReadinessCheck(Protocol):
    """A dependency whose absence makes the service not ready (the database)."""

    name: str

    def is_ready(self) -> bool: ...


def build_health_router(checks: Sequence[ReadinessCheck]) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health/liveness")
    def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @router.get("/health/readiness")
    def readiness(response: Response) -> dict[str, object]:
        failed = [check.name for check in checks if not check.is_ready()]
        if failed:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "failed": failed}
        return {"status": "ready"}

    return router
