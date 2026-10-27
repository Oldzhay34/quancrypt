from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

PROBLEM_BASE = "https://quancrypt.local/problems/"


def problem(status_code: int, code: str, title: str, detail: str | None = None) -> JSONResponse:
    """An RFC 9457 problem (contracts/openapi/ingest-api.yaml)."""
    body: dict[str, Any] = {"type": PROBLEM_BASE + code, "title": title, "status": status_code}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json")
