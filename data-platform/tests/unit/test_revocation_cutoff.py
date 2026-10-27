"""What a revocation leaves behind (D-296): a cut-off for its project key, so that erased data cannot come back, and a command
that no payload can talk its way out of."""

from __future__ import annotations

import logging
from uuid import UUID

import pytest

from quancrypt_data.domain.events import MAX_RECORD_NODES, QuarantineReason, exceeds_record_size
from quancrypt_data.port.inbound.ingest_events import IngestEventsResult
from tests.support.envelopes import KEY_A, KEY_B, envelope
from tests.unit.test_ingest_events_service import EVENT_1, EVENT_2, EVENT_3, REVOKE, Harness, revoked

NOON = "2026-10-27T12:00:00Z"  # the time of the fixed test clock


def stored_ids(harness: Harness) -> list[str]:
    return sorted(str(event_id) for event_id in harness.database.state.events)


class TestTheCutoff:
    def test_a_batch_sent_again_after_its_revocation_does_not_bring_the_data_back(self) -> None:
        harness = Harness()
        batch = [
            envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:00:00Z"),
            revoked(REVOKE, at="2026-10-27T10:00:05Z"),
        ]
        first = harness.ingest(*batch)

        again = harness.ingest(*batch)

        assert (first.accepted, first.consent_revoked) == (1, 1)
        assert again == IngestEventsResult(
            received=2, accepted=0, duplicate=1, quarantined=0, consent_revoked=0, superseded=1
        )
        assert stored_ids(harness) == []

    def test_an_older_event_that_arrives_after_the_revocation_is_dropped(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T10:00:00Z"))

        late = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T09:00:00Z"))

        assert (late.accepted, late.superseded) == (0, 1)
        assert stored_ids(harness) == []

    def test_an_event_at_the_very_moment_of_the_revocation_is_dropped_too(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T10:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:00:00Z"))

        assert result.superseded == 1

    def test_an_event_after_the_revocation_is_kept_the_consent_may_have_been_given_again(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T10:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:00:01Z"))

        assert (result.accepted, result.superseded) == (1, 0)

    def test_the_cutoff_is_the_latest_of_several_revocations(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T10:00:00Z"))
        harness.ingest(revoked(EVENT_3, at="2026-10-27T11:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:30:00Z"))

        assert result.superseded == 1

    def test_the_cutoff_belongs_to_one_project_only(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, key=KEY_A, at="2026-10-27T11:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, project_key=KEY_B, occurred_at="2026-10-27T10:00:00Z"))

        assert (result.accepted, result.superseded) == (1, 0)

    def test_a_quarantined_record_is_held_to_the_cutoff_too(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T11:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:00:00Z", payload={"bad": 1}))

        assert (result.quarantined, result.superseded) == (0, 1)
        assert harness.database.state.quarantine == {}

    def test_a_record_with_no_readable_time_cannot_be_placed_after_a_revocation_so_it_is_dropped(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T11:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, occurred_at="garbage"), {"project_key": KEY_A})

        assert (result.superseded, result.quarantined) == (2, 0)

    def test_a_revocation_whose_own_time_is_unreadable_is_dated_by_the_moment_it_was_received(self) -> None:
        harness = Harness()
        unreadable = revoked(REVOKE)
        unreadable["occurred_at"] = "garbage"
        harness.ingest(unreadable)

        old = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T11:59:00Z"))
        new = harness.ingest(envelope(event_id=EVENT_2, occurred_at="2026-10-27T12:00:01Z"))

        assert (old.superseded, new.accepted) == (1, 1)

    def test_the_audit_keeps_the_time_the_cutoff_comes_from(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T11:00:00Z"))

        assert harness.database.state.audit[UUID(REVOKE)].revoked_at.isoformat() == "2026-10-27T11:00:00+00:00"


class TestACommandIsACommand:
    def test_a_revocation_whose_payload_no_longer_matches_the_schema_still_erases(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1))
        newer = revoked(REVOKE)
        newer["payload"] = {"consent_type": "SOME_NEW_TYPE", "bad": True}

        with caplog.at_level(logging.WARNING, logger="quancrypt_data.usecase"):
            result = harness.ingest(newer)

        assert (result.consent_revoked, result.quarantined) == (1, 0)
        assert stored_ids(harness) == []
        assert "SOME_NEW_TYPE" not in caplog.text
        assert "did not match their schema" in caplog.text

    def test_a_revocation_with_a_key_that_is_not_a_project_key_is_only_quarantined(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1))
        broken = revoked(REVOKE, key="not-a-key")

        result = harness.ingest(broken)

        assert (result.consent_revoked, result.quarantined) == (0, 1)
        assert stored_ids(harness) == [EVENT_1]

    def test_a_revocation_with_a_bad_event_id_still_erases_and_a_repeat_of_it_is_recognised(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1))
        broken = revoked(REVOKE)
        broken["event_id"] = "nope"

        first = harness.ingest(broken)
        again = harness.ingest(broken)

        assert (first.consent_revoked, first.quarantined) == (1, 0)
        assert (again.consent_revoked, again.duplicate) == (0, 1)
        assert stored_ids(harness) == []

    def test_a_revocation_with_too_many_values_still_erases(self) -> None:
        harness = Harness()
        harness.ingest(envelope(event_id=EVENT_1))
        huge = revoked(REVOKE)
        huge["payload"] = {"values": list(range(MAX_RECORD_NODES))}

        result = harness.ingest(huge)

        assert (result.consent_revoked, result.quarantined) == (1, 0)
        assert stored_ids(harness) == []


class TestLateAndFutureRevocations:
    def test_an_older_revocation_that_arrives_late_is_audited_but_erases_nothing(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2026-10-27T10:00:00Z"))
        harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T10:30:00Z"))

        late = harness.ingest(revoked(EVENT_2, at="2026-10-27T09:00:00Z"))

        assert (late.consent_revoked, late.duplicate) == (1, 0)
        assert stored_ids(harness) == [EVENT_1]

    def test_a_revocation_dated_far_ahead_does_not_leave_a_cutoff_that_drops_the_next_events(self) -> None:
        harness = Harness()
        harness.ingest(revoked(REVOKE, at="2099-01-01T00:00:00Z"))

        result = harness.ingest(envelope(event_id=EVENT_1, occurred_at="2026-10-27T12:30:00Z"))

        assert (result.accepted, result.superseded) == (1, 0)


class TestWhatTheSenderCalledTheRecord:
    @pytest.mark.parametrize("name", ["a\x00b", "\ud800x", "x" * 65])
    def test_a_name_the_database_cannot_hold_is_not_kept_but_the_record_is_still_quarantined(self, name: str) -> None:
        harness = Harness()

        result = harness.ingest({"event_id": name, "project_key": KEY_A})

        assert result.quarantined == 1
        entry = next(iter(harness.database.state.quarantine.values()))
        assert entry.event_id is None
        assert entry.reason is QuarantineReason.MALFORMED_ENVELOPE


class TestSize:
    def test_a_record_with_too_many_values_is_refused_before_it_is_validated(self) -> None:
        harness = Harness()
        huge = envelope(event_id=EVENT_1, payload={"values": list(range(MAX_RECORD_NODES))})

        result = harness.ingest(huge)

        assert result.quarantined == 1
        entry = next(iter(harness.database.state.quarantine.values()))
        assert entry.message == "record: too many values"

    def test_the_counting_stops_early_and_handles_any_depth(self) -> None:
        nested: object = "leaf"
        for _ in range(5000):
            nested = [nested]
        assert not exceeds_record_size(nested)
        assert exceeds_record_size(list(range(10)), limit=5)
        assert not exceeds_record_size({"a": [1, 2], "b": {"c": 3}}, limit=10)


class TestOrder:
    def test_records_of_the_same_time_are_stored_in_the_same_order_whatever_the_order_sent(self) -> None:
        ids = [EVENT_3, EVENT_1, EVENT_2]
        forward = Harness()
        backward = Harness()

        forward.ingest(*[envelope(event_id=i) for i in ids])
        backward.ingest(*[envelope(event_id=i) for i in reversed(ids)])

        assert [str(i) for i in forward.database.state.events] == [str(i) for i in backward.database.state.events]
        assert [str(i) for i in forward.database.state.events] == sorted(ids)
