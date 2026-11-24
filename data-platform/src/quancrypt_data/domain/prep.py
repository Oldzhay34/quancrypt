"""The preprocessing pipeline as data (P6.4, data-preprocessing section 3): the raw events, the candidate rows of the
`prep` tables they turn into, the filters (Pipes and Filters) and what a filter sets aside.

Pure: no I/O, no framework. A candidate row keeps the event it came from (`source_event_id`) so that a filter can drop
or quarantine every row of an event, and so that the rows of one event always get the same identifiers (idempotency)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol

# The code lists of crypto-domain section 1; the migration seeds the same values into the prep lookup tables.
ALGORITHM_FAMILIES = frozenset({
    "RSA", "ECDSA", "ECDH", "EDDSA", "DH", "DSA", "ML_KEM", "ML_DSA", "SLH_DSA", "AES", "DES", "TRIPLE_DES",
    "CHACHA20", "SHA1", "SHA2", "SHA3", "MD5", "HMAC", "X25519", "HYBRID_X25519_MLKEM768", "UNKNOWN",
})  # fmt: skip
USAGE_CONTEXTS = frozenset({
    "TLS_KEY_EXCHANGE", "TLS_SERVER_AUTH", "MTLS_CLIENT_AUTH", "CERTIFICATE", "ENCRYPTION", "KEY_WRAP", "SIGNATURE",
    "TOKEN_SIGNATURE", "KEY_AGREEMENT", "HASH", "SYMMETRIC_ENCRYPTION", "KEYSTORE", "UNKNOWN",
})  # fmt: skip
LOCATION_KINDS = frozenset({"CODE", "CONFIG", "CERTIFICATE_FILE", "KEYSTORE_FILE", "BUILD_FILE", "TEST_CODE"})
PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
PROTOCOLS = frozenset({"HTTP", "GRPC", "MQTT", "AMQP", "KAFKA", "OTHER"})
SCOPE_DECISIONS = frozenset({"ALLOW", "DENY"})
SCOPE_RINGS = frozenset({"RULE_FILTER", "SCOPE_CLASSIFIER", "LLM_SELF_CHECK", "FAIL_CLOSED"})
LANGUAGES = frozenset({"tr", "en"})
PROJECT_ORIGINS = frozenset({"CORPUS", "BENCHMARK", "USER"})
# The reasons the pipeline sets a record aside (quarantine.error_code; schema-violation is shared with ingest-api).
PREP_ERROR_CODES = frozenset({"schema-violation", "type-mismatch", "identifier-leak", "secret-match"})
UNKNOWN = "UNKNOWN"
ROOT_UNIT = "."

# The filters in the order of data-preprocessing section 3 (the default of PREP_FILTER_ORDER).
FILTER_ORDER = (
    "SchemaValidator", "Deduplicator", "GeneratedCodeExcluder", "TestCodeFlagger", "Canonicalizer", "Anonymizer",
    "MissingValueHandler", "OutlierFlagger", "TypeCaster",
)  # fmt: skip

# A fixed namespace: the identifier of a prep row is derived from the raw event and the row's place in it.
_ROW_NAMESPACE = uuid.UUID("6c1b9a3e-5f0d-4a59-9d8e-0b6f0e3c2a11")


def row_id(source_event_id: str, kind: str, ordinal: int) -> str:
    return str(uuid.uuid5(_ROW_NAMESPACE, f"{source_event_id}:{kind}:{ordinal}"))


ANALYSIS_EVENTS = ("corpus_analysis", "benchmark_analysis")


@dataclass(frozen=True)
class RawEvent:
    """One row of raw.event, the payload as the JSON decoder gave it."""

    event_id: str
    event_type: str
    source: str
    schema_version: int
    occurred_at: datetime
    project_key: str
    payload: Mapping[str, object]


def event_unit(event: RawEvent) -> str:
    """The analysis unit an event's rows belong to: an analysis event names it, the other events are of the root."""
    path = event.payload.get("analysis_unit") if event.event_type in ANALYSIS_EVENTS else None
    return path if isinstance(path, str) else ROOT_UNIT


@dataclass(frozen=True)
class RawLabel:
    benchmark: str
    case_id: str
    file_path: str | None
    category: str | None
    cwe: int | None
    expected_vulnerable: bool


@dataclass(frozen=True)
class ProjectRow:
    project_key: str
    # CORPUS, BENCHMARK or USER (a project analysed for a user: core-service and agent-service events).
    origin: str
    is_outlier_project: bool = False


@dataclass(frozen=True)
class UnitRow:
    project_key: str
    unit_path: str
    java_version: object = None
    spring_boot_version: object = None


@dataclass(frozen=True)
class FindingRow:
    """A finding before the filters: values are as the event carried them (TypeCaster checks the types last)."""

    id: str
    source_event_id: str
    project_key: str
    unit_path: str
    file_path: object
    line_start: object
    line_end: object
    algorithm_family: object
    usage_context: object
    location_kind: object
    priority: object
    key_size_bits: object
    confidence: object
    mode: object = None
    padding: object = None
    hash: object = None
    library: object = None
    in_test_code: bool = False

    @property
    def full_path(self) -> str | None:
        """The path below the project root: a unit's path is relative to the unit (D-307b)."""
        if not isinstance(self.file_path, str):
            return None
        return self.file_path if self.unit_path == ROOT_UNIT else f"{self.unit_path}/{self.file_path}"


@dataclass(frozen=True)
class TopologyRow:
    project_key: str
    unit_path: str
    source_event_id: str
    node_count: object
    edge_count: object
    tls_edge_count: object
    mtls_edge_count: object


@dataclass(frozen=True)
class LinkRow:
    project_key: str
    unit_path: str
    source_event_id: str
    ordinal: int
    protocol: object
    tls: object
    mtls: object


@dataclass(frozen=True)
class ScopeRow:
    event_id: str
    project_key: str
    occurred_at: datetime
    decision: object
    confidence: object
    deciding_ring: object
    latency_ms: object
    language: object


@dataclass(frozen=True)
class LabelRow:
    benchmark: str
    case_id: str
    file_path: object
    category: object
    cwe: object
    expected_vulnerable: object


@dataclass(frozen=True)
class Rejection:
    """A record set aside by a filter: what it was (event or label) and why, never its content."""

    filter_code: str
    error_code: str
    message: str
    project_key: str | None = None
    raw_event_id: str | None = None
    label: tuple[str, str] | None = None
    # How many prep rows went with it (every row of a rejected event, or the one rejected row).
    rows: int = 1


@dataclass(frozen=True)
class PrepBatch:
    events: tuple[RawEvent, ...] = ()
    projects: tuple[ProjectRow, ...] = ()
    units: tuple[UnitRow, ...] = ()
    findings: tuple[FindingRow, ...] = ()
    topologies: tuple[TopologyRow, ...] = ()
    links: tuple[LinkRow, ...] = ()
    scopes: tuple[ScopeRow, ...] = ()
    labels: tuple[LabelRow, ...] = ()

    @property
    def size(self) -> int:
        """The rows the funnel counts: every prep row but the project and unit rows that hold the others."""
        return len(self.findings) + len(self.topologies) + len(self.links) + len(self.scopes) + len(self.labels)

    def without_events(self, event_ids: Iterable[str]) -> PrepBatch:
        """The batch without an event and every row that came from it."""
        gone = set(event_ids)
        if not gone:
            return self
        events = tuple(e for e in self.events if e.event_id not in gone)
        supported = {(e.project_key, event_unit(e)) for e in events}
        # A unit (and its runtime versions) or a project that only the removed events supported goes with them.
        chunk_zero_gone = {
            (e.project_key, event_unit(e))
            for e in self.events
            if e.event_id in gone and e.event_type in ANALYSIS_EVENTS and e.payload.get("chunk_index") == 0
        }
        units = tuple(
            UnitRow(u.project_key, u.unit_path) if (u.project_key, u.unit_path) in chunk_zero_gone else u
            for u in self.units
            if (u.project_key, u.unit_path) in supported
        )
        return replace(
            self,
            events=events,
            units=units,
            projects=tuple(p for p in self.projects if any(e.project_key == p.project_key for e in events)),
            findings=tuple(f for f in self.findings if f.source_event_id not in gone),
            topologies=tuple(t for t in self.topologies if t.source_event_id not in gone),
            links=tuple(link for link in self.links if link.source_event_id not in gone),
            scopes=tuple(s for s in self.scopes if s.event_id not in gone),
        )


@dataclass(frozen=True)
class FilterResult:
    batch: PrepBatch
    rejected: tuple[Rejection, ...] = ()
    # What a filter changed or found, by name (e.g. `canonicalised_to_unknown`); shown in the report.
    notes: Mapping[str, int] = field(default_factory=dict)


class RecordFilter(Protocol):
    """A step of the pipeline (data-preprocessing section 3): takes the batch, returns the batch it lets through and
    the records it set aside. A row it drops without a reason (a duplicate, generated code) is just not returned."""

    @property
    def code(self) -> str: ...

    def apply(self, batch: PrepBatch) -> FilterResult: ...


@dataclass(frozen=True)
class FilterCount:
    filter_code: str
    rows_in: int
    rows_out: int
    rows_rejected: int
    notes: Mapping[str, int]

    @property
    def rows_dropped(self) -> int:
        """Rows a filter removed without setting them aside (duplicates, generated code, rows of rejected events)."""
        return self.rows_in - self.rows_out - self.rows_rejected


def run_filters(
    batch: PrepBatch, filters: Sequence[RecordFilter]
) -> tuple[PrepBatch, list[Rejection], list[FilterCount]]:
    """Pipes and Filters: each filter takes what the previous one let through; the counters say where rows went."""
    rejected: list[Rejection] = []
    counts: list[FilterCount] = []
    for step in filters:
        before = batch.size
        result = step.apply(batch)
        batch = result.batch
        rejected.extend(result.rejected)
        counts.append(
            FilterCount(step.code, before, batch.size, sum(r.rows for r in result.rejected), dict(result.notes))
        )
    return batch, rejected, counts
