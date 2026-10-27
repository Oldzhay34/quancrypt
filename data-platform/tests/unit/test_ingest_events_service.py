from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from quancrypt_data.domain.events import MAX_BATCH_EVENTS, ProjectKeyTable, QuarantineReason
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand, IngestEventsResult, InvalidBatchError
from quancrypt_data.usecase.classification import EventClassifier
from quancrypt_data.usecase.delete_project_data_service import DeleteProjectDataService
from quancrypt_data.usecase.ingest_events_service import IngestEventsService
from tests.support.envelopes import KEY_A, KEY_B, PAYLOADS, envelope
from tests.support.fakes import (
    FakeAudit,
    FakeBatches,
    FakeDatabase,
    FakeEraser,
    FakeEvents,
    FakeLocks,
    FakeQuarantine,
    FakeRegistry,
    FakeValidator,
    FixedClock,
    SequentialIds,
)


class Harness:
    def __init__(self, *, fail_on: UUID | None = None) -> None:
        self.database = FakeDatabase()
        ids = SequentialIds()
        locks = FakeLocks(self.database)
        audit = FakeAudit(self.database)
        delete = DeleteProjectDataService(
            transactions=self.database,
            registry=FakeRegistry([ProjectKeyTable("raw", "event"), ProjectKeyTable("quarantine", "event")]),
            eraser=FakeEraser(self.database),
            audit=audit,
            locks=locks,
            clock=FixedClock(),
            ids=ids,
        )
        self.service = IngestEventsService(
            transactions=self.database,
            classifier=EventClassifier(FakeValidator(list(PAYLOADS))),
            events=FakeEvents(self.database, fail_on),
            quarantine=FakeQuarantine(self.database),
            batches=FakeBatches(self.database),
            locks=locks,
            audit=audit,
            delete_project_data=delete,
            clock=FixedClock(),
            ids=ids,
        )

    def ingest(self, *items: object) -> IngestEventsResult:
        return self.service.execute(IngestEventsCommand(items=items))


def revoked(event_id: str, *, key: str = KEY_A, at: str = "2026-10-27T11:00:00Z") -> dict[str, Any]:
    return envelope("consent_revoked", project_key=key, event_id=event_id, occurred_at=at)


EVENT_1 = "00000000-0000-4000-8000-000000000001"
EVENT_2 = "00000000-0000-4000-8000-000000000002"
EVENT_3 = "00000000-0000-4000-8000-000000000003"
REVOKE = "00000000-0000-4000-8000-0000000000ff"


class TestStoring:
    def test_valid_events_are_stored_with_their_source_and_the_batch(self) -> None:
        harness = Harness()

        result = harness.ingest(envelope(event_id=EVENT_1), envelope("scope_decision", event_id=EVENT_2))

        assert result == IngestEventsResult(
            received=2, accepted=2, duplicate=0, quarantined=0, consent_revoked=0, superseded=0
        )
        stored = harness.database.state.events
        assert stored[UUID(EVENT_1)].source.value == "core-service"
        assert stored[UUID(EVENT_2)].source.value == "agent-service"
        assert len(harness.database.state.batches) == 1
        assert stored[UUID(EVENT_1)].event.occurred_at.isoformat() == "2026-10-27T10:00:00+00:00"

    def test_the_same_event_twice_is_stored_once(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1))

        again = harness.ingest(envelope(event_id=EVENT_1), envelope(event_id=EVENT_1))

        assert again == IngestEventsResult(
            received=2, accepted=0, duplicate=2, quarantined=0, consent_revoked=0, superseded=0
        )
        assert len(harness.database.state.events) == 1
        # The batch row counts the duplicates of its own request.
        assert sorted(harness.database.state.batches.values()) == [(1, 0), (2, 2)]

    def test_a_repeat_inside_one_batch_counts_as_a_duplicate(self) -> None:
        harness = Harness()

        result = harness.ingest(envelope(event_id=EVENT_1), envelope(event_id=EVENT_1))

        assert (result.accepted, result.duplicate) == (1, 1)


class TestQuarantine:
    def test_a_bad_item_is_quarantined_and_does_not_fail_the_batch(self) -> None:
        harness = Harness()
        bad = envelope(event_id=EVENT_2, payload={"bad": 1})

        result = harness.ingest(envelope(event_id=EVENT_1), bad, "not an object", {"event_id": "x"})

        assert result == IngestEventsResult(
            received=4, accepted=1, duplicate=0, quarantined=3, consent_revoked=0, superseded=0
        )
        reasons = sorted(entry.reason for entry in harness.database.state.quarantine.values())
        assert reasons == sorted(
            [
                QuarantineReason.SCHEMA_VIOLATION,
                QuarantineReason.MALFORMED_ENVELOPE,
                QuarantineReason.MALFORMED_ENVELOPE,
            ]
        )

    def test_an_identical_bad_record_is_quarantined_once(self) -> None:
        harness = Harness()
        bad = envelope(event_id=EVENT_2, payload={"bad": 1})
        harness.ingest(bad)

        result = harness.ingest(bad)

        assert (result.quarantined, result.duplicate) == (0, 1)
        assert len(harness.database.state.quarantine) == 1

    def test_the_quarantine_keeps_a_valid_project_key_so_that_erasure_can_find_it(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_2, project_key=KEY_B, payload={"bad": 1}), {"project_key": "nope"})

        keys = sorted(str(entry.project_key) for entry in harness.database.state.quarantine.values())
        assert keys == ["None", KEY_B]

    def test_the_reason_message_never_repeats_a_value_of_the_record(self) -> None:
        harness = Harness()
        harness.ingest({"event_id": "ghp_secretvalue123", "payload": {"password": "hunter2"}})

        message = next(iter(harness.database.state.quarantine.values())).message
        assert "ghp_" not in message
        assert "hunter2" not in message

    def test_text_the_database_cannot_store_is_quarantined_as_a_marker(self) -> None:
        harness = Harness()

        result = harness.ingest(envelope(event_id=EVENT_1, payload={"bad": "a\x00b"}))

        assert result.quarantined == 1
        entry = next(iter(harness.database.state.quarantine.values()))
        assert entry.reason is QuarantineReason.MALFORMED_ENVELOPE
        assert entry.record == {"unstorable": True, "reason": "NUL character or lone surrogate"}

    def test_an_unknown_event_type_is_quarantined(self) -> None:
        harness = Harness()
        item = envelope(event_id=EVENT_1)
        item["event_type"] = "something_new"

        harness.ingest(item)

        entry = next(iter(harness.database.state.quarantine.values()))
        assert entry.reason is QuarantineReason.UNKNOWN_EVENT_TYPE

    def test_an_unreadable_timestamp_is_a_schema_violation(self) -> None:
        harness = Harness()

        harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27"))

        entry = next(iter(harness.database.state.quarantine.values()))
        assert entry.reason is QuarantineReason.SCHEMA_VIOLATION
        assert entry.message == "occurred_at: not an RFC 3339 timestamp"


class TestConsentRevoked:
    def test_it_erases_the_key_and_is_itself_not_stored(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1), envelope(event_id=EVENT_2, project_key=KEY_B))
        harness.ingest(envelope(event_id=EVENT_3, payload={"bad": 1}))

        result = harness.ingest(revoked(REVOKE))

        assert result == IngestEventsResult(
            received=1, accepted=0, duplicate=0, quarantined=0, consent_revoked=1, superseded=0
        )
        state = harness.database.state
        assert [str(i) for i in state.events] == [EVENT_2]
        assert state.quarantine == {}
        audit = state.audit[UUID(REVOKE)]
        assert audit.project_key == KEY_A
        assert dict(audit.deleted) == {"raw.event": 1, "quarantine.event": 1}

    def test_the_same_revocation_twice_does_nothing_the_second_time(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE))
        harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T12:30:00Z"))

        again = harness.ingest(revoked(REVOKE))

        assert (again.consent_revoked, again.duplicate) == (0, 1)
        # The data stored after the revocation survives a late repeat.
        assert [str(i) for i in harness.database.state.events] == [EVENT_1]

    def test_within_a_batch_events_are_applied_in_the_order_they_happened(self) -> None:
        harness = Harness()
        before = envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:00:00Z")
        after = envelope(event_id=EVENT_2, occurred_at="2026-10-27T12:00:00Z")

        # Sent in the "wrong" order on purpose.
        result = harness.ingest(after, revoked(REVOKE, at="2026-10-27T11:00:00Z"), before)

        assert (result.accepted, result.consent_revoked) == (2, 1)
        assert [str(i) for i in harness.database.state.events] == [EVENT_2]

    def test_other_keys_are_untouched(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1, project_key=KEY_B))

        harness.ingest(revoked(REVOKE, key=KEY_A))

        assert [str(i) for i in harness.database.state.events] == [EVENT_1]


class TestLocksAndLimits:
    def test_the_keys_of_the_whole_batch_are_locked_once_in_sorted_order(self) -> None:
        harness = Harness()

        harness.ingest(
            envelope(event_id=EVENT_1, project_key=KEY_B),
            envelope(event_id=EVENT_2, project_key=KEY_A, payload={"bad": 1}),
            envelope(event_id=EVENT_3, project_key=KEY_B),
        )

        assert harness.database.state.lock_calls[0] == [KEY_A, KEY_B]

    def test_an_empty_batch_is_refused(self) -> None:
        with pytest.raises(InvalidBatchError, match="empty"):
            Harness().ingest()

    def test_a_batch_above_the_limit_is_refused_and_nothing_is_written(self) -> None:
        harness = Harness()
        with pytest.raises(InvalidBatchError, match=str(MAX_BATCH_EVENTS)):
            harness.ingest(*[envelope() for _ in range(MAX_BATCH_EVENTS + 1)])
        assert harness.database.state.batches == {}

    def test_the_limit_itself_is_accepted(self) -> None:
        result = Harness().ingest(*[envelope() for _ in range(MAX_BATCH_EVENTS)])
        assert result.accepted == MAX_BATCH_EVENTS


class TestAtomicity:
    def test_a_failure_part_way_leaves_no_trace_of_the_batch(self) -> None:
        harness = Harness(fail_on=UUID(EVENT_2))
        harness.ingest(envelope(event_id=EVENT_3))
        batches_before = len(harness.database.state.batches)

        with pytest.raises(RuntimeError, match="storage failure"):
            harness.ingest(
                envelope(event_id=EVENT_1, occurred_at="2026-10-27T09:00:00Z"),
                revoked(REVOKE, at="2026-10-27T09:30:00Z"),
                envelope(event_id=EVENT_2),
            )

        after = harness.database.state
        assert sorted(str(i) for i in after.events) == [EVENT_3]
        assert after.audit == {}
        assert len(after.batches) == batches_before == 1
