from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

from quancrypt_data.domain.events import (
    MAX_BATCH_EVENTS,
    SOURCE_BY_EVENT_TYPE,
    has_unstorable_text,
    storable_record,
)
from quancrypt_data.port.inbound.delete_project_data import DeleteProjectDataCommand, DeleteProjectDataUseCase
from quancrypt_data.port.inbound.ingest_events import (
    IngestEventsCommand,
    IngestEventsResult,
    IngestEventsUseCase,
    InvalidBatchError,
)
from quancrypt_data.port.outbound.erasure import ErasureAudit, ProjectKeyLock
from quancrypt_data.port.outbound.storage import BatchStore, EventStore, QuarantineEntry, QuarantineStore
from quancrypt_data.port.outbound.system import Clock, IdGenerator
from quancrypt_data.port.outbound.transaction import TransactionRunner
from quancrypt_data.usecase.classification import Classified, EventClassifier

_LOG = logging.getLogger("quancrypt_data.usecase")

# A revocation dated further ahead of the time it was received than this is treated as received now, so a wrong clock
# cannot leave a cut-off that drops the key's later events for ever (D-297b). The tolerance is a chosen value, not a
# measurement.
FUTURE_TOLERANCE = timedelta(minutes=5)


class IngestEventsService(IngestEventsUseCase):
    """Writes a batch of event envelopes to the landing layer in one transaction (D-295, D-296).

    Every item is checked against its schema; an item that fails is quarantined, not refused, so the sender's retry loop
    ends. Storing is idempotent on `event_id`. A `consent_revoked` record is a command: it is not stored, it erases the
    key's rows (DeleteProjectData) at its place in the batch order and it sets the cut-off of the key: a record of
    the same
    project that happened at or before the latest revocation is dropped (`superseded`), so neither a retried batch
    nor a late
    one can bring erased data back. The constructor takes ten collaborators because each is a separate narrow port
    (ISP) and
    `_write` follows the steps of the transaction plan in order (docs/data/warehouse_raw-erd.md section 6).
    """

    def __init__(
        self,
        transactions: TransactionRunner,
        classifier: EventClassifier,
        events: EventStore,
        quarantine: QuarantineStore,
        batches: BatchStore,
        locks: ProjectKeyLock,
        audit: ErasureAudit,
        delete_project_data: DeleteProjectDataUseCase,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._transactions = transactions
        self._classifier = classifier
        self._events = events
        self._quarantine = quarantine
        self._batches = batches
        self._locks = locks
        self._audit = audit
        self._delete = delete_project_data
        self._clock = clock
        self._ids = ids

    def execute(self, command: IngestEventsCommand) -> IngestEventsResult:
        items = command.items
        if not items:
            raise InvalidBatchError("the batch is empty")
        if len(items) > MAX_BATCH_EVENTS:
            raise InvalidBatchError(f"the batch holds more than {MAX_BATCH_EVENTS} events")
        # Checking is pure: it runs once, outside the transaction (which may be repeated).
        classified = [self._classifier.classify(position, item) for position, item in enumerate(items)]
        ordered = sorted(classified, key=lambda c: (c.sort_at, c.order_key, c.position))
        keys = sorted({c.project_key for c in classified if c.project_key is not None})
        return self._transactions.run(lambda: self._write(len(items), ordered, keys))

    def _write(self, received: int, ordered: list[Classified], keys: list[str]) -> IngestEventsResult:
        self._locks.acquire(keys)
        received_at = self._clock.now()
        batch_id = self._ids.new_id()
        self._batches.start(batch_id, received_at, received)
        # What each key may still store: nothing at or before its latest revocation (read under the key's lock).
        cutoffs: dict[str, datetime] = {}
        for key in keys:
            latest = self._audit.latest_revocation(key)
            if latest is not None:
                cutoffs[key] = latest
        accepted = duplicate = quarantined = revoked = superseded = 0
        invalid_commands = 0
        for entry in ordered:
            if entry.revocation is not None:
                command = entry.revocation
                if not command.schema_valid:
                    invalid_commands += 1
                at = min(command.occurred_at or received_at, received_at + FUTURE_TOLERANCE)
                covered = cutoffs.get(command.project_key)
                # An older revocation that arrives late is audited but erases nothing: what is stored happened after it.
                erased = self._delete.execute(
                    DeleteProjectDataCommand(
                        project_key=command.project_key,
                        event_id=command.event_id,
                        occurred_at=at,
                        erase_rows=covered is None or at > covered,
                    )
                ).erased
                revoked += erased
                duplicate += not erased
                if erased:
                    cutoffs[command.project_key] = max(at, cutoffs.get(command.project_key, at))
                continue
            cutoff = cutoffs.get(entry.project_key) if entry.project_key is not None else None
            if cutoff is not None and entry.sort_at <= cutoff:
                superseded += 1
            elif entry.rejection is not None and entry.record_sha256 is not None:
                stored = self._quarantine.insert_if_absent(
                    QuarantineEntry(
                        id=self._ids.new_id(),
                        batch_id=batch_id,
                        event_id=_sender_event_id(entry.item),
                        project_key=entry.project_key,
                        record_sha256=entry.record_sha256,
                        record=storable_record(entry.item),
                        reason=entry.rejection.reason,
                        message=entry.rejection.message,
                        quarantined_at=received_at,
                    )
                )
                quarantined += stored
                duplicate += not stored
            elif entry.event is not None:
                source = SOURCE_BY_EVENT_TYPE[entry.event.event_type]
                stored = self._events.insert_if_absent(entry.event, source, batch_id, received_at)
                accepted += stored
                duplicate += not stored
        if invalid_commands:
            # A count only, never the record: a revocation whose payload no longer matches its schema was still
            # carried out.
            _LOG.warning(
                "%d consent_revoked commands did not match their schema and were carried out anyway", invalid_commands
            )
        self._batches.finish(batch_id, duplicate)
        return IngestEventsResult(received, accepted, duplicate, quarantined, revoked, superseded)


def _sender_event_id(item: object) -> str | None:
    """What the sender called the record, when that text can be stored: a NUL character or a lone surrogate would
    make the
    database refuse the row, and with it the whole batch for ever."""
    value = item.get("event_id") if isinstance(item, Mapping) else None
    if isinstance(value, str) and len(value) <= 64 and not has_unstorable_text(value):
        return value
    return None
