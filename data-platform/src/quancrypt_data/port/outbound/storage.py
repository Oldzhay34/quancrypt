from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from quancrypt_data.domain.events import Event, EventSource, QuarantineReason


@dataclass(frozen=True)
class QuarantineEntry:
    id: UUID
    batch_id: UUID
    # What the sender called the record; text, because a bad record may carry anything.
    event_id: str | None
    # Only a valid project key (the key erasure matches on); None when the record has none.
    project_key: str | None
    record_sha256: str
    record: object
    reason: QuarantineReason
    message: str
    quarantined_at: datetime


class BatchStore(Protocol):
    def start(self, batch_id: UUID, received_at: datetime, received_count: int) -> None: ...

    def finish(self, batch_id: UUID, duplicate_count: int) -> None: ...


class EventStore(Protocol):
    def insert_if_absent(self, event: Event, source: EventSource, batch_id: UUID, received_at: datetime) -> bool:
        """Store the event; False (and no change) when an event with this id is already stored."""
        ...


class QuarantineStore(Protocol):
    def insert_if_absent(self, entry: QuarantineEntry) -> bool:
        """Store the entry; False (and no change) when an identical record (same fingerprint) is already quarantined."""
        ...
