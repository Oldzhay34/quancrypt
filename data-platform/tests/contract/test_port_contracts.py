"""Contract tests of the outbound ports (solid-checklist L, hexagonal-service section 7): the in-memory test double and the real
PostgreSQL adapter of every port pass the same tests, so the doubles the unit tests rely on cannot drift from the adapters."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from quancrypt_data.domain.events import Event, EventSource, ProjectKeyTable, QuarantineReason
from quancrypt_data.infrastructure.persistence.repositories import (
    PostgresBatchStore,
    PostgresErasureAudit,
    PostgresEventStore,
    PostgresProjectDataEraser,
    PostgresProjectKeyLock,
    PostgresQuarantineStore,
    StaticProjectKeyTableRegistry,
)
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog
from quancrypt_data.port.outbound.erasure import ErasureAudit, ErasureRecord, ProjectDataEraser, ProjectKeyLock
from quancrypt_data.port.outbound.storage import BatchStore, EventStore, QuarantineEntry, QuarantineStore
from quancrypt_data.port.outbound.transaction import TransactionRunner
from quancrypt_data.port.outbound.validation import EnvelopeValidator
from tests.support.envelopes import KEY_A, KEY_B, PAYLOADS, envelope
from tests.support.fakes import (
    NOW,
    FakeAudit,
    FakeBatches,
    FakeDatabase,
    FakeEraser,
    FakeEvents,
    FakeLocks,
    FakeQuarantine,
    FakeValidator,
)

SCHEMAS = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "events"


@dataclass
class Adapters:
    runner: TransactionRunner
    events: EventStore
    quarantine: QuarantineStore
    batches: BatchStore
    audit: ErasureAudit
    eraser: ProjectDataEraser
    locks: ProjectKeyLock
    count_events: Callable[[str], int]
    count_quarantine: Callable[[str], int]

    def in_transaction(self, work: Callable[[], Any]) -> Any:
        return self.runner.run(work)

    def new_batch(self) -> uuid.UUID:
        batch_id = uuid.uuid4()
        self.batches.start(batch_id, NOW, 1)
        return batch_id

    def add_event(self, batch_id: uuid.UUID, *, key: str = KEY_A, event_id: uuid.UUID | None = None) -> bool:
        event = Event(event_id or uuid.uuid4(), "finding_detected", 1, NOW, key, dict(PAYLOADS["finding_detected"]))
        return self.events.insert_if_absent(event, EventSource.CORE_SERVICE, batch_id, NOW)

    def add_quarantined(self, batch_id: uuid.UUID, *, key: str | None = KEY_A, sha: str | None = None) -> bool:
        entry = QuarantineEntry(
            id=uuid.uuid4(),
            batch_id=batch_id,
            event_id=None,
            project_key=key,
            record_sha256=sha or uuid.uuid4().hex * 2,
            record={"a": 1},
            reason=QuarantineReason.SCHEMA_VIOLATION,
            message="$: required",
            quarantined_at=NOW,
        )
        return self.quarantine.insert_if_absent(entry)


@pytest.fixture(params=["fake", pytest.param("postgres", marks=pytest.mark.postgres)])
def adapters(request: pytest.FixtureRequest) -> Adapters:
    if request.param == "fake":
        database = FakeDatabase()
        return Adapters(
            runner=database,
            events=FakeEvents(database),
            quarantine=FakeQuarantine(database),
            batches=FakeBatches(database),
            audit=FakeAudit(database),
            eraser=FakeEraser(database),
            locks=FakeLocks(database),
            count_events=lambda key: sum(1 for s in database.state.events.values() if s.event.project_key == key),
            count_quarantine=lambda key: sum(1 for e in database.state.quarantine.values() if e.project_key == key),
        )
    stack = request.getfixturevalue("stack")
    database = stack.container.database
    engine = stack.instance.migrator_engine()

    def count(table: str) -> Callable[[str], int]:
        def run(key: str) -> int:
            with engine.begin() as connection:
                return int(
                    connection.execute(
                        text(f"SELECT count(*) FROM {table} WHERE project_key = :k"), {"k": key}
                    ).scalar_one()
                )

        return run

    return Adapters(
        runner=database,
        events=PostgresEventStore(database),
        quarantine=PostgresQuarantineStore(database),
        batches=PostgresBatchStore(database),
        audit=PostgresErasureAudit(database),
        eraser=PostgresProjectDataEraser(database, StaticProjectKeyTableRegistry()),
        locks=PostgresProjectKeyLock(database),
        count_events=count("raw.event"),
        count_quarantine=count("quarantine.event"),
    )


class TestTransactionRunner:
    def test_the_value_of_the_work_is_returned_and_its_writes_are_kept(self, adapters: Adapters) -> None:
        def work() -> str:
            adapters.add_event(adapters.new_batch())
            return "done"

        assert adapters.in_transaction(work) == "done"
        assert adapters.count_events(KEY_A) == 1

    def test_a_failure_rolls_the_writes_back_and_the_same_exception_comes_out(self, adapters: Adapters) -> None:
        class Boom(Exception):
            pass

        def work() -> None:
            adapters.add_event(adapters.new_batch())
            raise Boom

        with pytest.raises(Boom):
            adapters.in_transaction(work)
        assert adapters.count_events(KEY_A) == 0

    def test_a_nested_call_takes_part_in_the_open_transaction(self, adapters: Adapters) -> None:
        def inner() -> None:
            adapters.add_event(adapters.new_batch())

        def outer() -> None:
            adapters.runner.run(inner)
            raise RuntimeError("after the inner call returned")

        with pytest.raises(RuntimeError):
            adapters.in_transaction(outer)
        assert adapters.count_events(KEY_A) == 0


class TestStores:
    def test_an_event_is_stored_once(self, adapters: Adapters) -> None:
        event_id = uuid.uuid4()

        def work() -> tuple[bool, bool, bool]:
            batch = adapters.new_batch()
            return (
                adapters.add_event(batch, event_id=event_id),
                adapters.add_event(batch, event_id=event_id),
                adapters.add_event(batch),
            )

        assert adapters.in_transaction(work) == (True, False, True)
        assert adapters.count_events(KEY_A) == 2

    def test_a_quarantined_record_is_stored_once(self, adapters: Adapters) -> None:
        def work() -> tuple[bool, bool, bool]:
            batch = adapters.new_batch()
            return (
                adapters.add_quarantined(batch, sha="a" * 64),
                adapters.add_quarantined(batch, sha="a" * 64),
                adapters.add_quarantined(batch, sha="b" * 64, key=None),
            )

        assert adapters.in_transaction(work) == (True, False, True)
        assert adapters.count_quarantine(KEY_A) == 1

    def test_a_batch_can_be_started_and_finished(self, adapters: Adapters) -> None:
        def work() -> None:
            batch = adapters.new_batch()
            adapters.batches.finish(batch, 0)

        adapters.in_transaction(work)


class TestErasure:
    def seed(self, adapters: Adapters) -> None:
        def work() -> None:
            batch = adapters.new_batch()
            adapters.add_event(batch, key=KEY_A)
            adapters.add_event(batch, key=KEY_A)
            adapters.add_event(batch, key=KEY_B)
            adapters.add_quarantined(batch, key=KEY_A)

        adapters.in_transaction(work)

    def test_the_eraser_deletes_the_rows_of_the_key_only_and_says_how_many(self, adapters: Adapters) -> None:
        self.seed(adapters)

        deleted = adapters.in_transaction(
            lambda: (
                adapters.eraser.delete(ProjectKeyTable("raw", "event"), KEY_A),
                adapters.eraser.delete(ProjectKeyTable("quarantine", "event"), KEY_A),
            )
        )

        assert deleted == (2, 1)
        assert (adapters.count_events(KEY_A), adapters.count_events(KEY_B), adapters.count_quarantine(KEY_A)) == (
            0,
            1,
            0,
        )

    def test_the_eraser_refuses_a_table_that_is_not_registered(self, adapters: Adapters) -> None:
        with pytest.raises(ValueError, match="registry"):
            adapters.in_transaction(lambda: adapters.eraser.delete(ProjectKeyTable("prep", "finding"), KEY_A))

    def test_the_audit_remembers_an_erasure_and_its_cutoff(self, adapters: Adapters) -> None:
        first, second = uuid.uuid4(), uuid.uuid4()

        def record(event_id: uuid.UUID, at: datetime) -> None:
            adapters.audit.record(
                ErasureRecord(uuid.uuid4(), NOW, event_id, KEY_A, at, {"raw.event": 1, "quarantine.event": 0})
            )

        def work() -> tuple[Any, ...]:
            before = (adapters.audit.is_recorded(first), adapters.audit.latest_revocation(KEY_A))
            record(first, NOW - timedelta(hours=2))
            record(second, NOW - timedelta(hours=1))
            return (
                *before,
                adapters.audit.is_recorded(first),
                adapters.audit.is_recorded(uuid.uuid4()),
                adapters.audit.latest_revocation(KEY_A),
                adapters.audit.latest_revocation(KEY_B),
            )

        assert adapters.in_transaction(work) == (False, None, True, False, NOW - timedelta(hours=1), None)

    def test_a_lock_can_be_taken_again_in_the_same_transaction_in_any_order(self, adapters: Adapters) -> None:
        def work() -> None:
            adapters.locks.acquire([KEY_B, KEY_A])
            adapters.locks.acquire([KEY_A])
            adapters.locks.acquire([])

        adapters.in_transaction(work)


def validators() -> Sequence[Any]:
    return [
        pytest.param(lambda: FakeValidator(list(PAYLOADS)), id="fake"),
        pytest.param(lambda: JsonSchemaCatalog(SCHEMAS), id="json-schema-catalog"),
    ]


class TestEnvelopeValidator:
    @pytest.fixture(params=validators())
    def validator(self, request: pytest.FixtureRequest) -> EnvelopeValidator:
        make: Callable[[], EnvelopeValidator] = request.param
        return make()

    def test_it_knows_the_event_types_it_has_a_schema_for(self, validator: EnvelopeValidator) -> None:
        assert all(validator.knows(name) for name in PAYLOADS)
        assert not validator.knows("made_up")

    def test_a_valid_envelope_has_no_violation(self, validator: EnvelopeValidator) -> None:
        assert list(validator.violations(envelope("finding_detected"))) == []

    def test_an_invalid_envelope_has_violations_that_name_no_value(self, validator: EnvelopeValidator) -> None:
        secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        item = envelope("finding_detected", payload={"bad": secret})

        reasons = list(validator.violations(item))

        assert reasons
        assert secret not in " ".join(reasons)

    def test_an_unknown_type_is_a_violation_not_an_exception(self, validator: EnvelopeValidator) -> None:
        item = envelope("finding_detected")
        item["event_type"] = "made_up"

        assert list(validator.violations(item))
