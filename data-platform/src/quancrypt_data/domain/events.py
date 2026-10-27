"""Event envelope rules of the landing layer (contracts/schemas/events/*.json, D-20, D-295).

The domain knows what an event is, where it comes from and what makes a record unstorable; it knows no JSON Schema
library (that is an outbound port) and no database.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

# D-295a: one request carries at most this many events (the body limit of 8 MiB is an HTTP concern).
MAX_BATCH_EVENTS = 500
# A quarantined original above this size is replaced by a marker (the hash still identifies it).
MAX_QUARANTINE_RECORD_BYTES = 64 * 1024
MAX_MESSAGE_CHARS = 500
# A record with more containers and values than this is refused before it is validated: the cost of validating,
# hashing and
# storing a record grows with its size (a valid topology event of 1000 links has about 5000).
MAX_RECORD_NODES = 20_000

CONSENT_REVOKED = "consent_revoked"

_PROJECT_KEY = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")


class EventSource(StrEnum):
    """Who produced an event (ingest.event_source). The envelope does not say; the event type does (D-233a)."""

    CORE_SERVICE = "core-service"
    AGENT_SERVICE = "agent-service"


# `scope_decision` is the only agent event; core-service produces the other seven.
SOURCE_BY_EVENT_TYPE: Mapping[str, EventSource] = MappingProxyType(
    {
        "finding_detected": EventSource.CORE_SERVICE,
        "topology_recorded": EventSource.CORE_SERVICE,
        "scan_completed": EventSource.CORE_SERVICE,
        "plan_created": EventSource.CORE_SERVICE,
        "plan_item_transitioned": EventSource.CORE_SERVICE,
        "project_runtime_changed": EventSource.CORE_SERVICE,
        CONSENT_REVOKED: EventSource.CORE_SERVICE,
        "scope_decision": EventSource.AGENT_SERVICE,
    }
)


class QuarantineReason(StrEnum):
    """quarantine.error_code."""

    MALFORMED_ENVELOPE = "malformed-envelope"
    UNKNOWN_EVENT_TYPE = "unknown-event-type"
    SCHEMA_VIOLATION = "schema-violation"


@dataclass(frozen=True)
class Event:
    """A valid envelope. `payload` is the inner body only (core D-142)."""

    event_id: UUID
    event_type: str
    schema_version: int
    occurred_at: datetime
    project_key: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class Revocation:
    """A consent_revoked command: erase the project key. It stays a command when its payload no longer matches the
    schema
    (a new consent type, a newer schema version): failing to erase would be failing open (D-296)."""

    event_id: UUID
    project_key: str
    # None when the sender's time is unreadable (the service then uses the time it received the request).
    occurred_at: datetime | None
    schema_valid: bool


@dataclass(frozen=True)
class Rejection:
    reason: QuarantineReason
    # Names the failing path and rule, never a value from the record (it may be arbitrary data).
    message: str


@dataclass(frozen=True)
class ProjectKeyTable:
    """A table that holds rows of a project key (the registry of D-295d lists them)."""

    schema: str
    name: str

    def __post_init__(self) -> None:
        if not (re.fullmatch(r"[a-z_]+", self.schema) and re.fullmatch(r"[a-z_]+", self.name)):
            raise ValueError("a table identifier is lower-case letters and underscores only")

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"


def is_project_key(value: object) -> bool:
    return isinstance(value, str) and _PROJECT_KEY.fullmatch(value) is not None


def require_project_key(value: str) -> str:
    if not is_project_key(value):
        raise ValueError("project_key must be 64 lower-case hexadecimal digits")
    return value


def project_key_of(item: object) -> str | None:
    """The record's project key when it is a valid one (the only key rows can be erased by), else None."""
    if isinstance(item, Mapping):
        value = item.get("project_key")
        if is_project_key(value):
            return str(value)
    return None


def has_unstorable_text(value: object) -> bool:
    """True when a string (or an object key) holds a NUL character or a lone surrogate: PostgreSQL's jsonb refuses both,
    and one such record would fail its whole batch for ever (poison pill; agent-service D-237a analogue). Iterative on
    purpose."""
    pending: list[object] = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(ch == "\x00" or "\ud800" <= ch <= "\udfff" for ch in current):
                return True
        elif isinstance(current, Mapping):
            for key, child in current.items():
                pending.append(key)
                pending.append(child)
        elif isinstance(current, list):
            pending.extend(current)
    return False


def exceeds_record_size(value: object, limit: int = MAX_RECORD_NODES) -> bool:
    """True when the record holds more than `limit` containers and values (iterative, stops early)."""
    count = 0
    pending: list[object] = [value]
    while pending:
        current = pending.pop()
        count += 1
        if count > limit:
            return True
        if isinstance(current, Mapping):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


def parse_timestamp(value: object) -> datetime | None:
    """An RFC 3339 timestamp in UTC (the `date-time` of the schemas, which jsonschema does not check without an extra
    package)."""
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def fingerprint(item: object) -> str:
    """SHA-256 of the canonical JSON of the original record: the same record always has the same fingerprint (idempotent
    quarantine)."""
    canonical = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def storable_record(item: object) -> object:
    """The record as the quarantine stores it: itself, or a marker when it cannot or should not be stored verbatim."""
    if has_unstorable_text(item):
        return {"unstorable": True, "reason": "NUL character or lone surrogate"}
    size = len(json.dumps(item, separators=(",", ":"), ensure_ascii=True))
    if size > MAX_QUARANTINE_RECORD_BYTES:
        return {"truncated": True, "size_bytes": size}
    return item


def clip_message(message: str) -> str:
    return message if len(message) <= MAX_MESSAGE_CHARS else message[: MAX_MESSAGE_CHARS - 1] + "…"
