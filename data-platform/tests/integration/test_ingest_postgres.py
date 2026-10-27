"""The use cases against the real database: what is stored, what is quarantined, what an erasure removes (acid-3nf-database
section 7: atomicity, idempotency, KVKK erasure)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from quancrypt_data.port.inbound.delete_project_data import DeleteProjectDataCommand
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand, IngestEventsResult, InvalidBatchError
from tests.conftest import Stack
from tests.support.envelopes import KEY_A, KEY_B, PAYLOADS, envelope

pytestmark = pytest.mark.postgres


def rows(stack: Stack, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    with stack.instance.migrator_engine().begin() as connection:
        return [tuple(row) for row in connection.execute(text(sql), params)]


def count(stack: Stack, table: str, where: str = "true", **params: Any) -> int:
    return int(rows(stack, f"SELECT count(*) FROM {table} WHERE {where}", **params)[0][0])


def ingest(stack: Stack, *items: object) -> IngestEventsResult:
    return stack.container.ingest_events.execute(IngestEventsCommand(items=items))


def revoked(*, key: str = KEY_A, at: str = "2026-10-27T11:00:00Z", event_id: str | None = None) -> dict[str, Any]:
    return envelope("consent_revoked", project_key=key, occurred_at=at, event_id=event_id)


@pytest.fixture
def failing_trigger(migrated: Any) -> Iterator[Any]:
    """Makes every INSERT into a table fail: the way to prove that a batch is all or nothing."""
    created: list[str] = []

    def install(table: str) -> None:
        name = "fail_" + table.replace(".", "_")
        with migrated.migrator_engine().begin() as connection:
            connection.execute(
                text(
                    f"CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    "BEGIN RAISE EXCEPTION 'injected failure'; END $$"
                )
            )
            connection.execute(
                text(f"CREATE TRIGGER {name} BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION public.{name}()")
            )
        created.append(table)

    yield install
    for table in created:
        name = "fail_" + table.replace(".", "_")
        with migrated.migrator_engine().begin() as connection:
            connection.execute(text(f"DROP TRIGGER {name} ON {table}"))
            connection.execute(text(f"DROP FUNCTION public.{name}()"))


class TestStoring:
    def test_every_event_type_is_stored_with_its_lineage(self, stack: Stack) -> None:
        items = [envelope(name, event_id=str(uuid.uuid4())) for name in PAYLOADS if name != "consent_revoked"]

        result = ingest(stack, *items)

        assert (result.received, result.accepted, result.duplicate, result.quarantined) == (7, 7, 0, 0)
        stored = rows(
            stack, "SELECT event_type, source, source_ref, schema_version, project_key FROM raw.event ORDER BY 1"
        )
        assert [row[0] for row in stored] == sorted(name for name in PAYLOADS if name != "consent_revoked")
        assert {row[1] for row in stored} == {"core-service", "agent-service"}
        assert {row[2] for row in stored} == {None}
        assert {(row[3], row[4]) for row in stored} == {(1, KEY_A)}
        assert rows(stack, "SELECT received_count, duplicate_count FROM ingest.ingest_batch") == [(7, 0)]

    def test_the_payload_and_the_event_time_are_kept(self, stack: Stack) -> None:
        item = envelope("scan_completed", occurred_at="2026-10-09T10:00:00.5Z")

        ingest(stack, item)

        payload, occurred_at = rows(stack, "SELECT payload, occurred_at FROM raw.event")[0]
        assert payload == item["payload"]
        assert occurred_at.isoformat() == "2026-10-09T10:00:00.500000+00:00"

    def test_the_same_event_twice_is_stored_once(self, stack: Stack) -> None:
        item = envelope()

        first = ingest(stack, item)
        second = ingest(stack, item, item)

        assert (first.accepted, second.accepted, second.duplicate) == (1, 0, 2)
        assert count(stack, "raw.event") == 1
        assert sorted(rows(stack, "SELECT received_count, duplicate_count FROM ingest.ingest_batch")) == [
            (1, 0),
            (2, 2),
        ]


class TestQuarantine:
    def test_a_bad_record_is_kept_whole_with_its_reason_and_the_batch_still_goes_through(self, stack: Stack) -> None:
        bad = envelope(payload={"priority": "P9"})

        result = ingest(stack, envelope(), bad, "not an object", ["a list"])

        assert (result.accepted, result.quarantined) == (1, 3)
        record, code, message, key = rows(
            stack,
            "SELECT record, error_code, error_message, project_key FROM quarantine.event WHERE event_id = :id",
            id=bad["event_id"],
        )[0]
        assert record == bad
        assert code == "schema-violation"
        assert "P9" not in message
        assert key == KEY_A
        assert count(stack, "quarantine.event") == 3

    def test_the_same_bad_record_again_is_quarantined_once(self, stack: Stack) -> None:
        bad = envelope(payload={"surprise": 1})
        ingest(stack, bad)

        again = ingest(stack, bad)

        assert (again.quarantined, again.duplicate) == (0, 1)
        assert count(stack, "quarantine.event") == 1

    def test_text_the_database_cannot_store_is_quarantined_not_a_poison_pill(self, stack: Stack) -> None:
        # A NUL character and a lone surrogate would make jsonb refuse the whole batch for ever (HTTP 500, endless retry).
        result = ingest(stack, envelope(), {"note": "a\x00b"}, {"note": "\ud800"}, envelope(payload={"x": "a\x00b"}))

        assert (result.accepted, result.quarantined) == (1, 3)
        records = [row[0] for row in rows(stack, "SELECT record FROM quarantine.event")]
        assert {"unstorable": True, "reason": "NUL character or lone surrogate"} in records
        assert not any("\x00" in json.dumps(record) for record in records)

    def test_a_very_large_record_is_kept_as_a_size_marker(self, stack: Stack) -> None:
        ingest(stack, {"blob": "x" * 200_000})

        record = rows(stack, "SELECT record FROM quarantine.event")[0][0]
        assert record["truncated"] is True
        assert record["size_bytes"] > 200_000

    def test_an_unknown_event_type_and_a_missing_id_are_told_apart(self, stack: Stack) -> None:
        unknown = envelope()
        unknown["event_type"] = "made_up"

        ingest(stack, unknown, {"event_type": "finding_detected"})

        assert sorted(code for (code,) in rows(stack, "SELECT error_code FROM quarantine.event")) == [
            "malformed-envelope",
            "unknown-event-type",
        ]


class TestErasure:
    def test_a_revocation_removes_the_key_from_raw_and_quarantine_and_is_audited(self, stack: Stack) -> None:
        ingest(stack, envelope(), envelope("scan_completed"), envelope(project_key=KEY_B))
        ingest(stack, envelope(payload={"priority": "P9"}), envelope(project_key=KEY_B, payload={"priority": "P9"}))
        revocation = revoked()

        result = ingest(stack, revocation)

        assert result == IngestEventsResult(
            received=1, accepted=0, duplicate=0, quarantined=0, consent_revoked=1, superseded=0
        )
        assert count(stack, "raw.event", "project_key = :k", k=KEY_A) == 0
        assert count(stack, "quarantine.event", "project_key = :k", k=KEY_A) == 0
        # Another project is untouched, and the revocation itself is not kept in raw.
        assert count(stack, "raw.event", "project_key = :k", k=KEY_B) == 1
        assert count(stack, "quarantine.event", "project_key = :k", k=KEY_B) == 1
        assert count(stack, "raw.event", "event_id = :id", id=revocation["event_id"]) == 0
        audit = rows(stack, "SELECT id, action_code, project_key, event_id FROM ingest.ingest_audit")
        assert [(a[1], a[2], str(a[3])) for a in audit] == [("PROJECT_DATA_DELETED", KEY_A, revocation["event_id"])]
        detail = rows(
            stack, "SELECT table_name, deleted_rows FROM ingest.ingest_audit_table WHERE audit_id = :id", id=audit[0][0]
        )
        assert sorted(detail) == [("quarantine.event", 1), ("raw.event", 2)]

    def test_an_event_that_follows_the_revocation_in_the_same_batch_survives_it(self, stack: Stack) -> None:
        before = envelope(occurred_at="2026-10-27T10:00:00Z")
        after = envelope(occurred_at="2026-10-27T12:00:00Z")

        result = ingest(stack, after, revoked(at="2026-10-27T11:00:00Z"), before)

        assert (result.accepted, result.consent_revoked) == (2, 1)
        assert [str(i) for (i,) in rows(stack, "SELECT event_id FROM raw.event")] == [after["event_id"]]

    def test_a_late_repeat_of_the_same_revocation_does_not_erase_what_came_after(self, stack: Stack) -> None:
        revocation = revoked()
        ingest(stack, revocation)
        newer = envelope(occurred_at="2026-10-27T13:00:00Z")
        ingest(stack, newer)

        again = ingest(stack, revocation)

        assert (again.consent_revoked, again.duplicate) == (0, 1)
        assert count(stack, "raw.event", "event_id = :id", id=newer["event_id"]) == 1
        assert count(stack, "ingest.ingest_audit") == 1

    def test_the_use_case_can_be_called_on_its_own(self, stack: Stack) -> None:
        ingest(stack, envelope(), envelope(project_key=KEY_B))

        result = stack.container.delete_project_data.execute(
            DeleteProjectDataCommand(project_key=KEY_A, event_id=uuid.uuid4(), occurred_at=datetime.now(UTC))
        )

        assert result.erased
        assert dict(result.deleted) == {"raw.event": 1, "quarantine.event": 0}
        assert count(stack, "raw.event") == 1


class TestAtomicity:
    def test_a_failure_in_the_quarantine_leaves_no_event_and_no_batch(self, stack: Stack, failing_trigger: Any) -> None:
        failing_trigger("quarantine.event")

        with pytest.raises(DBAPIError, match="injected failure"):
            ingest(stack, envelope(), envelope(payload={"priority": "P9"}))

        assert count(stack, "raw.event") == 0
        assert count(stack, "quarantine.event") == 0
        assert count(stack, "ingest.ingest_batch") == 0

    def test_a_failing_audit_rolls_the_deletion_back(self, stack: Stack, failing_trigger: Any) -> None:
        ingest(stack, envelope(), envelope("scan_completed"))
        failing_trigger("ingest.ingest_audit")

        with pytest.raises(DBAPIError, match="injected failure"):
            ingest(stack, revoked())

        # The rows are still there: an erasure is never half done, and it is retried as a whole.
        assert count(stack, "raw.event", "project_key = :k", k=KEY_A) == 2
        assert count(stack, "ingest.ingest_audit") == 0

    def test_a_failure_in_the_audit_detail_undoes_the_deletion_and_the_events_of_the_batch(
        self, stack: Stack, failing_trigger: Any
    ) -> None:
        old = envelope(occurred_at="2026-10-27T09:00:00Z")
        ingest(stack, old)
        failing_trigger("ingest.ingest_audit_table")

        with pytest.raises(DBAPIError, match="injected failure"):
            ingest(stack, revoked(at="2026-10-27T10:00:00Z"), envelope(occurred_at="2026-10-27T11:00:00Z"))

        assert [str(i) for (i,) in rows(stack, "SELECT event_id FROM raw.event")] == [old["event_id"]]
        assert count(stack, "ingest.ingest_audit") == 0
        assert stack.container.database.retries == 0

    def test_a_batch_that_was_refused_as_a_whole_writes_nothing(self, stack: Stack) -> None:
        with pytest.raises(InvalidBatchError):
            stack.container.ingest_events.execute(IngestEventsCommand(items=[]))

        assert count(stack, "ingest.ingest_batch") == 0


def test_a_connection_is_not_left_inside_a_transaction(stack: Stack) -> None:
    engine: Engine = stack.instance.migrator_engine()
    ingest(stack, envelope())
    with engine.connect() as connection:
        idle = connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = 'warehouse_db' AND state = 'idle in transaction'"
            )
        ).scalar_one()
    assert idle == 0


class TestReviewFindings:
    @pytest.mark.parametrize("name", ["a\x00b", "\ud800x"])
    def test_a_record_name_the_database_cannot_hold_does_not_fail_the_batch(self, stack: Stack, name: str) -> None:
        result = ingest(stack, envelope(), {"event_id": name, "project_key": KEY_A})

        assert (result.accepted, result.quarantined) == (1, 1)
        assert rows(stack, "SELECT count(*) FROM quarantine.event WHERE event_id IS NULL") == [(1,)]

    def test_a_batch_sent_again_after_its_revocation_does_not_bring_the_data_back(self, stack: Stack) -> None:
        batch = [
            envelope(occurred_at="2026-10-27T10:00:00Z"),
            envelope("consent_revoked", occurred_at="2026-10-27T10:00:05Z"),
        ]
        first = ingest(stack, *batch)

        again = ingest(stack, *batch)

        assert (first.accepted, first.consent_revoked) == (1, 1)
        assert (again.accepted, again.superseded, again.duplicate) == (0, 1, 1)
        assert count(stack, "raw.event") == 0
        assert (
            rows(stack, "SELECT revoked_at FROM ingest.ingest_audit")[0][0].isoformat() == "2026-10-27T10:00:05+00:00"
        )

    def test_an_older_event_that_arrives_later_in_another_request_is_dropped_the_newer_one_kept(
        self, stack: Stack
    ) -> None:
        ingest(stack, envelope("consent_revoked", occurred_at="2026-10-27T10:00:00Z"))

        late = ingest(
            stack,
            envelope(occurred_at="2026-10-27T09:59:59Z"),
            envelope(payload={"priority": "P9"}, occurred_at="2026-10-27T09:00:00Z"),
        )
        newer = ingest(stack, envelope(occurred_at="2026-10-27T10:00:01Z"))

        assert (late.accepted, late.quarantined, late.superseded) == (0, 0, 2)
        assert newer.accepted == 1
        assert (count(stack, "raw.event"), count(stack, "quarantine.event")) == (1, 0)

    def test_a_revocation_that_no_longer_matches_the_schema_still_erases(self, stack: Stack) -> None:
        ingest(stack, envelope())
        future = envelope("consent_revoked", payload={"consent_type": "SOMETHING_NEW", "delete_requested": False})

        result = ingest(stack, future)

        assert (result.consent_revoked, result.quarantined) == (1, 0)
        assert count(stack, "raw.event") == 0
        assert count(stack, "ingest.ingest_audit") == 1

    def test_a_record_with_too_many_values_is_quarantined_not_validated(self, stack: Stack) -> None:
        result = ingest(stack, envelope(payload={"values": list(range(30_000))}))

        assert result.quarantined == 1
        record = rows(stack, "SELECT record, error_message FROM quarantine.event")[0]
        assert record[0]["truncated"] is True
        assert record[1] == "record: too many values"
