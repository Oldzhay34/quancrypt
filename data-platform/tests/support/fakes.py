"""In-memory test doubles of the outbound ports (unit tests only: no network, no database)."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from quancrypt_data.domain.events import Event, EventSource, ProjectKeyTable
from quancrypt_data.port.outbound.erasure import ErasureRecord
from quancrypt_data.port.outbound.storage import QuarantineEntry

NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)


@dataclass
class StoredEvent:
    event: Event
    source: EventSource
    batch_id: UUID


@dataclass
class State:
    events: dict[UUID, StoredEvent] = field(default_factory=dict)
    quarantine: dict[str, QuarantineEntry] = field(default_factory=dict)
    batches: dict[UUID, tuple[int, int]] = field(default_factory=dict)
    audit: dict[UUID, ErasureRecord] = field(default_factory=dict)
    lock_calls: list[list[str]] = field(default_factory=list)
    # Rows of project-key tables other than the two landing tables (a registry that grows): table -> project keys.
    other_rows: dict[str, list[str]] = field(default_factory=dict)


class FakeDatabase:
    """Holds the state and runs work like a transaction: a failure puts the state back as it was; a nested call joins."""

    def __init__(self) -> None:
        self.state = State()
        self._depth = 0
        self.runs = 0

    def run[T](self, work: Callable[[], T]) -> T:
        if self._depth > 0:
            return work()
        self.runs += 1
        snapshot = copy.deepcopy(self.state)
        self._depth += 1
        try:
            return work()
        except BaseException:
            self.state = snapshot
            raise
        finally:
            self._depth -= 1


class FakeValidator:
    """Knows the given types; an envelope is invalid when its payload has a `bad` key."""

    def __init__(self, known: Sequence[str]) -> None:
        self._known = set(known)

    def knows(self, event_type: str) -> bool:
        return event_type in self._known

    def violations(self, item: object) -> Sequence[str]:
        event_type = item.get("event_type") if isinstance(item, Mapping) else None
        if not isinstance(event_type, str) or event_type not in self._known:
            return ["event_type: no schema for this type"]
        payload = item.get("payload") if isinstance(item, Mapping) else None
        if isinstance(payload, Mapping) and "bad" in payload:
            return ["$.payload: additionalProperties"]
        return []


class FakeBatches:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def start(self, batch_id: UUID, received_at: datetime, received_count: int) -> None:
        self._database.state.batches[batch_id] = (received_count, 0)

    def finish(self, batch_id: UUID, duplicate_count: int) -> None:
        received, _ = self._database.state.batches[batch_id]
        self._database.state.batches[batch_id] = (received, duplicate_count)


class FakeEvents:
    def __init__(self, database: FakeDatabase, fail_on: UUID | None = None) -> None:
        self._database = database
        self.fail_on = fail_on

    def insert_if_absent(self, event: Event, source: EventSource, batch_id: UUID, received_at: datetime) -> bool:
        if event.event_id == self.fail_on:
            raise RuntimeError("storage failure")
        if event.event_id in self._database.state.events:
            return False
        self._database.state.events[event.event_id] = StoredEvent(event, source, batch_id)
        return True


class FakeQuarantine:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def insert_if_absent(self, entry: QuarantineEntry) -> bool:
        if entry.record_sha256 in self._database.state.quarantine:
            return False
        self._database.state.quarantine[entry.record_sha256] = entry
        return True


class FakeLocks:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def acquire(self, project_keys: Sequence[str]) -> None:
        self._database.state.lock_calls.append(list(project_keys))


class FakeRegistry:
    def __init__(self, tables: Sequence[ProjectKeyTable]) -> None:
        self._tables = tuple(tables)

    def tables(self) -> Sequence[ProjectKeyTable]:
        return self._tables


class FakeEraser:
    """Deletes from the in-memory stores: `raw.event` and `quarantine.event` by project key."""

    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def delete(self, table: ProjectKeyTable, project_key: str) -> int:
        state = self._database.state
        if table.qualified == "raw.event":
            ids = [i for i, stored in state.events.items() if stored.event.project_key == project_key]
            for event_id in ids:
                del state.events[event_id]
            return len(ids)
        if table.qualified == "quarantine.event":
            hashes = [h for h, entry in state.quarantine.items() if entry.project_key == project_key]
            for digest in hashes:
                del state.quarantine[digest]
            return len(hashes)
        if table.qualified in state.other_rows:
            rows = state.other_rows[table.qualified]
            kept = [key for key in rows if key != project_key]
            deleted = len(rows) - len(kept)
            state.other_rows[table.qualified] = kept
            return deleted
        # Like the real adapter: a table that is not registered is refused.
        raise ValueError("the table is not in the project-key registry")


class FakeAudit:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def is_recorded(self, event_id: UUID) -> bool:
        return event_id in self._database.state.audit

    def record(self, record: ErasureRecord) -> None:
        self._database.state.audit[record.event_id] = record

    def latest_revocation(self, project_key: str) -> datetime | None:
        times = [r.revoked_at for r in self._database.state.audit.values() if r.project_key == project_key]
        return max(times) if times else None


class FixedClock:
    def now(self) -> datetime:
        return NOW


class SequentialIds:
    def __init__(self) -> None:
        self._next = 0

    def new_id(self) -> UUID:
        self._next += 1
        return UUID(int=self._next)
