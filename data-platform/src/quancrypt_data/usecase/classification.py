"""Decides what an item of a batch is: a valid event, a revocation command or a rejection with a reason (never an
exception)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from quancrypt_data.domain.events import (
    CONSENT_REVOKED,
    SOURCE_BY_EVENT_TYPE,
    Event,
    QuarantineReason,
    Rejection,
    Revocation,
    clip_message,
    exceeds_record_size,
    fingerprint,
    has_unstorable_text,
    parse_timestamp,
    project_key_of,
)
from quancrypt_data.port.outbound.validation import EnvelopeValidator

_EARLIEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Classified:
    position: int
    item: object
    event: Event | None
    rejection: Rejection | None
    revocation: Revocation | None
    # A valid project key of the item (also of a quarantined one: erasure must find it); None otherwise.
    project_key: str | None
    # Where the item sorts in the batch: its occurred_at when it has a readable one.
    sort_at: datetime
    # Breaks a tie of `sort_at` the same way for every batch (the event id, or the fingerprint of a rejected record),
    # so two
    # requests that carry the same records always take their unique-index waits in the same order.
    order_key: str
    # SHA-256 of a rejected record (what the quarantine deduplicates on); None otherwise.
    record_sha256: str | None


class EventClassifier:
    def __init__(self, validator: EnvelopeValidator) -> None:
        self._validator = validator

    def classify(self, position: int, item: object) -> Classified:
        project_key = project_key_of(item)
        sort_at = _EARLIEST
        if isinstance(item, Mapping):
            sort_at = parse_timestamp(item.get("occurred_at")) or _EARLIEST
        revocation = self._revocation(item)
        outcome = None if revocation is not None else self._read(item)
        if isinstance(outcome, Event):
            return Classified(
                position, item, outcome, None, None, project_key, outcome.occurred_at, str(outcome.event_id), None
            )
        if revocation is not None:
            return Classified(
                position, item, None, None, revocation, project_key, sort_at, str(revocation.event_id), None
            )
        digest = fingerprint(item)
        return Classified(position, item, None, outcome, None, project_key, sort_at, digest, digest)

    def _revocation(self, item: object) -> Revocation | None:
        """A consent_revoked record with a valid project key is a command whatever its payload or event id looks like:
        the schema is not allowed to decide whether an erasure happens (a newer schema version must not make it fail
        open)."""
        if not isinstance(item, Mapping) or item.get("event_type") != CONSENT_REVOKED:
            return None
        project_key = project_key_of(item)
        if project_key is None:
            return None
        event_id = _uuid(item.get("event_id"))
        well_formed = event_id is not None and not has_unstorable_text(item) and not exceeds_record_size(item)
        if event_id is None:
            # A broken id must not stop the erasure (D-297c): the record's fingerprint stands in, so a repeat of it is
            # still recognised.
            event_id = uuid5(NAMESPACE_URL, fingerprint(item))
        valid = well_formed and self._validator.knows(CONSENT_REVOKED) and not self._validator.violations(item)
        return Revocation(event_id, project_key, parse_timestamp(item.get("occurred_at")), schema_valid=valid)

    def _read(self, item: object) -> Event | Rejection:
        if not isinstance(item, Mapping):
            return Rejection(QuarantineReason.MALFORMED_ENVELOPE, "record: not a JSON object")
        if has_unstorable_text(item):
            return Rejection(QuarantineReason.MALFORMED_ENVELOPE, "record: NUL character or lone surrogate in a string")
        if exceeds_record_size(item):
            return Rejection(QuarantineReason.MALFORMED_ENVELOPE, "record: too many values")
        event_id = _uuid(item.get("event_id"))
        if event_id is None:
            return Rejection(QuarantineReason.MALFORMED_ENVELOPE, "event_id: not a UUID")
        event_type = item.get("event_type")
        if not isinstance(event_type, str):
            return Rejection(QuarantineReason.MALFORMED_ENVELOPE, "event_type: not a string")
        if event_type not in SOURCE_BY_EVENT_TYPE or not self._validator.knows(event_type):
            return Rejection(QuarantineReason.UNKNOWN_EVENT_TYPE, "event_type: no schema for this type")
        issues = self._validator.violations(item)
        if issues:
            return Rejection(QuarantineReason.SCHEMA_VIOLATION, clip_message("; ".join(issues)))
        occurred_at = parse_timestamp(item.get("occurred_at"))
        if occurred_at is None:
            return Rejection(QuarantineReason.SCHEMA_VIOLATION, "occurred_at: not an RFC 3339 timestamp")
        project_key = project_key_of(item)
        if project_key is None:
            # The schema pattern is matched with `search`, so a key with a trailing line break passes it; the domain
            # does not.
            return Rejection(QuarantineReason.SCHEMA_VIOLATION, "project_key: not 64 lower-case hexadecimal digits")
        payload = item.get("payload")
        version = item.get("schema_version")
        if not isinstance(payload, Mapping) or not isinstance(version, int):
            return Rejection(QuarantineReason.SCHEMA_VIOLATION, "payload or schema_version: wrong type")
        return Event(event_id, event_type, version, occurred_at, project_key, payload)


def _uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
