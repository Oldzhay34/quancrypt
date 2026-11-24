"""SnippetSource over the analyzer's `GET /api/v1/snippets` (contracts/openapi/analyzer-service.yaml): the analyzer
reads the file below its read-only /corpus mount and redacts it (D-179, D-180). Loopback only, no proxy, no redirect
(D-301c)."""

from __future__ import annotations

import httpx

from quancrypt_ml.domain.labels import SourceLocation
from quancrypt_ml.port.outbound.labeling import AnalyzerUnavailableError, SnippetUnavailableError

MAX_CONTEXT = 10  # the analyzer's limit
# The analyzer answers these for a location it will not or cannot read: the row gets no context, the export goes on.
_LOCATION_STATUSES = frozenset({400, 404, 422})


class AnalyzerSnippetClient:
    def __init__(
        self, base_url: str, token: str, timeout_s: float = 30.0, transport: httpx.BaseTransport | None = None
    ):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-Internal-Token": token, "Accept": "application/json"},
            timeout=timeout_s,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    def context(self, location: SourceLocation, radius: int) -> tuple[tuple[int, str], ...]:
        if location.line is None:
            raise SnippetUnavailableError("no line")
        params: dict[str, str | int] = {
            "root": location.root, "path": location.path, "line": location.line, "context": min(radius, MAX_CONTEXT),
        }  # fmt: skip
        try:
            response = self._client.get("/api/v1/snippets", params=params)
        except httpx.HTTPError:
            raise AnalyzerUnavailableError("the analyzer cannot be reached") from None
        if response.status_code in _LOCATION_STATUSES:
            raise SnippetUnavailableError(f"analyzer status {response.status_code}")
        if response.status_code != 200:
            raise AnalyzerUnavailableError(f"analyzer status {response.status_code}")
        try:
            lines = response.json()["lines"]
            return tuple((int(item["number"]), str(item["text"])) for item in lines)
        except (ValueError, KeyError, TypeError):
            raise AnalyzerUnavailableError("the analyzer answer is not a snippet") from None

    def close(self) -> None:
        self._client.close()
