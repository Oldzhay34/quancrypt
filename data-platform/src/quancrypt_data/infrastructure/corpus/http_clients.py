"""HTTP adapters of the corpus tooling: analyzer-service and ingest-api, both on this machine.

Both clients ignore proxy environment variables, follow no redirect and send the service token in `X-Internal-Token`.
Their messages name the status or the exception class and never repeat an answer. Only connection failures and 502/503
are tried again (a 503 of ingest-api means "too many batches in flight, send it again", D-297d)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import httpx

from quancrypt_data.domain.corpus_events import (
    PROTOCOLS,
    AnalysisStats,
    CorpusFinding,
    Runtime,
    TopologySummary,
    UnitAnalysis,
)
from quancrypt_data.port.outbound.corpus import (
    AnalysisFailedError,
    AnalysisUnsupportedError,
    DeliveryResult,
    EventDeliveryError,
)

_RETRIED_STATUSES = frozenset({502, 503})
TOKEN_HEADER = "X-Internal-Token"  # noqa: S105 (a header name)


def new_client(timeout_s: float, token: str) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout_s, connect=5.0),
        headers={TOKEN_HEADER: token},
        trust_env=False,
        follow_redirects=False,
    )


def _post(
    client: httpx.Client, url: str, body: object, attempts: int, sleep: Callable[[float], None]
) -> httpx.Response:
    """POST with a pause (1, 2, 4... seconds) between attempts; returns the last answer, raises the last connection
    error."""
    last: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            sleep(float(2 ** (attempt - 1)))
        try:
            response = client.post(url, json=body)
        except httpx.ConnectError as exc:
            last = exc
            continue
        if response.status_code in _RETRIED_STATUSES and attempt + 1 < attempts:
            continue
        return response
    assert last is not None  # noqa: S101 (reached only when every attempt failed to connect)
    raise last


def _non_negative(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


class HttpCodeAnalyzer:
    """analyzer-service (`POST /api/v1/analyses` and `/topologies`, contracts/openapi/analyzer-service.yaml)."""

    def __init__(
        self, base_url: str, client: httpx.Client, sleep: Callable[[float], None] = time.sleep, attempts: int = 3
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client
        self._sleep = sleep
        self._attempts = attempts

    def analyze(self, root: str) -> UnitAnalysis:
        body = self._request("/api/v1/analyses", {"root": root, "include_tests": True})
        runtime = _mapping(body.get("runtime"))
        stats = _mapping(body.get("stats"))
        raw_findings = body.get("findings")
        if not isinstance(raw_findings, list):
            raise AnalysisFailedError("the analyzer answered with an unexpected shape")
        findings = tuple(self._finding(item) for item in raw_findings)
        return UnitAnalysis(
            unit=".",
            runtime=Runtime(_text(runtime.get("java_version")), _text(runtime.get("spring_boot_version"))),
            findings=findings,
            stats=AnalysisStats(
                _non_negative(stats.get("files_scanned")),
                _non_negative(stats.get("findings_total")) or len(findings),
                _non_negative(stats.get("duration_ms")),
            ),
            topology=None,
        )

    def topology(self, root: str) -> TopologySummary | None:
        try:
            body = self._request("/api/v1/topologies", {"root": root})
        except AnalysisUnsupportedError:
            return None
        edges = [e for e in body.get("edges", []) if isinstance(e, dict)] if isinstance(body.get("edges"), list) else []
        raw_nodes = body.get("nodes")
        nodes = raw_nodes if isinstance(raw_nodes, list) else []
        counts = dict.fromkeys(PROTOCOLS, 0)
        for edge in edges:
            protocol = edge.get("protocol")
            counts[protocol if protocol in counts else "OTHER"] += 1
        return TopologySummary(
            node_count=len(nodes),
            edge_count=len(edges),
            tls_edge_count=sum(1 for e in edges if e.get("tls") is True),
            mtls_edge_count=sum(1 for e in edges if e.get("mtls") is True),
            protocol_counts=counts,
        )

    def _request(self, path: str, body: Mapping[str, object]) -> dict[str, Any]:
        try:
            response = _post(self._client, self._base + path, body, self._attempts, self._sleep)
        except httpx.HTTPError as exc:
            raise AnalysisFailedError(f"analyzer-service is not reachable ({type(exc).__name__})") from None
        if response.status_code == 422:
            raise AnalysisUnsupportedError("the analyzer cannot analyse this root")
        if response.status_code != 200:
            raise AnalysisFailedError(f"analyzer-service answered {response.status_code}")
        try:
            parsed = response.json()
        except ValueError:
            raise AnalysisFailedError("analyzer-service answered with invalid JSON") from None
        if not isinstance(parsed, dict):
            raise AnalysisFailedError("the analyzer answered with an unexpected shape")
        return parsed

    @staticmethod
    def _finding(item: object) -> CorpusFinding:
        if not isinstance(item, dict):
            raise AnalysisFailedError("the analyzer answered with an unexpected shape")
        try:
            return CorpusFinding(
                file=item["file"],
                line_start=item["line_start"],
                line_end=item["line_end"],
                raw_name=item["raw_name"],
                algorithm_family=item["algorithm_family"],
                usage_context=item["usage_context"],
                location_kind=item["location_kind"],
                priority=item["priority"],
                key_size_bits=item["key_size_bits"],
                mode=item.get("mode"),
                padding=item.get("padding"),
                hash=item.get("hash"),
                library=item.get("library"),
                confidence=float(item["confidence"]),
            )
        except (KeyError, TypeError, ValueError):
            raise AnalysisFailedError("a finding of the analyzer lacks a field") from None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


class HttpEventSink:
    """ingest-api (`POST /api/v1/events`, contracts/openapi/ingest-api.yaml)."""

    def __init__(
        self, url: str, client: httpx.Client, sleep: Callable[[float], None] = time.sleep, attempts: int = 5
    ) -> None:
        self._url = url
        self._client = client
        self._sleep = sleep
        self._attempts = attempts

    def send(self, events: Sequence[Mapping[str, object]]) -> DeliveryResult:
        try:
            response = _post(self._client, self._url, list(events), self._attempts, self._sleep)
        except httpx.HTTPError as exc:
            raise EventDeliveryError(f"ingest-api is not reachable ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise EventDeliveryError(f"ingest-api answered {response.status_code}")
        try:
            answer = response.json()
        except ValueError:
            raise EventDeliveryError("ingest-api answered with invalid JSON") from None
        if not isinstance(answer, dict):
            raise EventDeliveryError("ingest-api answered with an unexpected shape")
        return DeliveryResult(
            accepted=_non_negative(answer.get("accepted")),
            duplicate=_non_negative(answer.get("duplicate")),
            quarantined=_non_negative(answer.get("quarantined")),
            superseded=_non_negative(answer.get("superseded")),
            consent_revoked=_non_negative(answer.get("consent_revoked")),
        )
