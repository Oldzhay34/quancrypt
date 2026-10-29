"""What an analysis of a corpus project or a benchmark becomes: the `corpus_analysis` and `benchmark_analysis` events
(P6.2).

The payload holds coded fields, numbers and paths relative to the analysis root only: no repository address, no local
path, no commit id, no symbol and no code (contracts/schemas/events/corpus_analysis.json). The event id is derived
from what the event is about, so running the same analysis again is recognised by ingest-api as a duplicate
(idempotent)."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid5

from quancrypt_data.domain.corpus import RepoRef

CORPUS_ANALYSIS: Final = "corpus_analysis"
BENCHMARK_ANALYSIS: Final = "benchmark_analysis"
# ingest-api limits a record to 20,000 values (D-296i) and a finding takes about fifteen: 800 per event leaves room.
MAX_FINDINGS_PER_EVENT: Final = 800
ROOT_UNIT: Final = "."
# Fixed namespace of the derived event ids (any change would make every earlier run look new).
_EVENT_NAMESPACE: Final = UUID("6f0d0c9e-3a52-4c5e-9d1b-0a6e7b1f2c11")
PROTOCOLS: Final = ("HTTP", "GRPC", "MQTT", "AMQP", "KAFKA", "OTHER")
_UNIT_SEGMENT = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def is_valid_unit(unit: str) -> bool:
    """A unit the event schema accepts: `.`, or one or two path segments of plain characters (no segment of dots
    only)."""
    if unit == ROOT_UNIT:
        return True
    segments = unit.split("/")
    return 1 <= len(segments) <= 2 and all(_UNIT_SEGMENT.fullmatch(s) is not None and set(s) != {"."} for s in segments)


@dataclass(frozen=True)
class CorpusFinding:
    file: str
    line_start: int | None
    line_end: int | None
    raw_name: str
    algorithm_family: str
    usage_context: str
    location_kind: str
    priority: str
    key_size_bits: int | None
    mode: str | None
    padding: str | None
    hash: str | None
    library: str | None
    confidence: float

    def payload(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "raw_name": self.raw_name,
            "algorithm_family": self.algorithm_family,
            "usage_context": self.usage_context,
            "location_kind": self.location_kind,
            "priority": self.priority,
            "key_size_bits": self.key_size_bits,
            "mode": self.mode,
            "padding": self.padding,
            "hash": self.hash,
            "library": self.library,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Runtime:
    java_version: str | None
    spring_boot_version: str | None


@dataclass(frozen=True)
class TopologySummary:
    node_count: int
    edge_count: int
    tls_edge_count: int
    mtls_edge_count: int
    protocol_counts: Mapping[str, int]

    def payload(self) -> dict[str, object]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "tls_edge_count": self.tls_edge_count,
            "mtls_edge_count": self.mtls_edge_count,
            "protocol_counts": {protocol: self.protocol_counts.get(protocol, 0) for protocol in PROTOCOLS},
        }


@dataclass(frozen=True)
class AnalysisStats:
    files_scanned: int
    findings_total: int
    duration_ms: int


@dataclass(frozen=True)
class UnitAnalysis:
    """The analysis of one unit: the repository root (`.`) or one of its directories with a build file."""

    unit: str
    runtime: Runtime
    findings: tuple[CorpusFinding, ...]
    stats: AnalysisStats
    topology: TopologySummary | None


def project_key(salt: str, identifier: str) -> str:
    """HMAC-SHA256 of the identifier, keyed with the salt text (UTF-8), as lower-case hexadecimal: the same
    derivation as
    core-service's, so one key never means two projects (D-129, D-162e)."""
    return hmac.new(salt.encode("utf-8"), identifier.encode("utf-8"), hashlib.sha256).hexdigest()


def repo_identifier(repo: RepoRef) -> str:
    # A prefix of its own, like `benchmark:`: a user project of the same repository (core-service hashes the bare
    # address) must
    # never get the same key as the corpus project, or its consent revocation would erase the corpus rows (D-301).
    return f"corpus:{repo.canonical}"


def benchmark_identifier(benchmark: str) -> str:
    return f"benchmark:{benchmark}"


def build_events(
    event_type: str,
    key: str,
    units: Sequence[UnitAnalysis],
    occurred_at: datetime,
    *,
    benchmark: str | None = None,
) -> list[dict[str, object]]:
    """One event per unit and chunk of at most `MAX_FINDINGS_PER_EVENT` findings; the topology summary rides on the
    first
    chunk."""
    events: list[dict[str, object]] = []
    stamp = occurred_at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    for unit in units:
        chunks = [
            unit.findings[i : i + MAX_FINDINGS_PER_EVENT] for i in range(0, len(unit.findings), MAX_FINDINGS_PER_EVENT)
        ]
        chunks = chunks or [()]
        for index, chunk in enumerate(chunks):
            payload: dict[str, object] = {
                "analysis_unit": unit.unit,
                "chunk_index": index,
                "chunk_count": len(chunks),
                "runtime": {
                    "java_version": unit.runtime.java_version,
                    "spring_boot_version": unit.runtime.spring_boot_version,
                },
                "findings": [finding.payload() for finding in chunk],
                "topology": unit.topology.payload() if unit.topology is not None and index == 0 else None,
                "stats": {
                    "files_scanned": unit.stats.files_scanned,
                    "findings_total": unit.stats.findings_total,
                    "duration_ms": unit.stats.duration_ms,
                },
            }
            if benchmark is not None:
                payload = {"benchmark": benchmark, **payload}
            events.append(
                {
                    "event_id": str(uuid5(_EVENT_NAMESPACE, f"{key}:{event_type}:{unit.unit}:{index}")),
                    "event_type": event_type,
                    "schema_version": 1,
                    "occurred_at": stamp,
                    "project_key": key,
                    "payload": payload,
                }
            )
    return events
