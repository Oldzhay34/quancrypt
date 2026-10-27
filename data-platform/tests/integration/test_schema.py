"""The warehouse_db landing layer as the migration builds it (real PostgreSQL, the project's own init scripts and roles)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from quancrypt_data.domain.events import SOURCE_BY_EVENT_TYPE, QuarantineReason
from quancrypt_data.infrastructure.persistence.database import apply_migrations
from quancrypt_data.infrastructure.persistence.repositories import StaticProjectKeyTableRegistry
from tests.support.envelopes import KEY_A
from tests.support.postgres import MIGRATIONS_DIR, PostgresInstance

pytestmark = pytest.mark.postgres

NOW = "2026-10-27T12:00:00Z"


def rows(engine: Engine, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    with engine.begin() as connection:
        result = connection.execute(text(sql), params)
        return [tuple(row) for row in result] if result.returns_rows else []


def refused(engine: Engine, sql: str, fragment: str, **params: Any) -> None:
    with pytest.raises(DBAPIError) as caught:
        rows(engine, sql, **params)
    assert fragment in str(caught.value.orig)


def seed_batch(instance: PostgresInstance, *, received: int = 1) -> uuid.UUID:
    batch_id = uuid.uuid4()
    rows(
        instance.migrator_engine(),
        "INSERT INTO ingest.ingest_batch (id, received_at, received_count) VALUES (:id, :now, :n)",
        id=batch_id,
        now=NOW,
        n=received,
    )
    return batch_id


def event_insert(**overrides: Any) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "event_id": uuid.uuid4(),
        "source": "core-service",
        "event_type": "finding_detected",
        "version": 1,
        "key": KEY_A,
        "payload": "{}",
        **overrides,
    }
    sql = (
        "INSERT INTO raw.event (event_id, batch_id, source, event_type, schema_version, occurred_at, received_at, "
        "project_key, payload) VALUES (:event_id, :batch_id, :source, :event_type, :version, :now, :now, :key, "
        "CAST(:payload AS jsonb))"
    )
    return sql, {**params, "now": NOW}


class TestShape:
    def test_the_schemas_and_tables_are_what_the_design_says(self, migrated: PostgresInstance) -> None:
        tables = {
            f"{schema}.{name}"
            for schema, name in rows(
                migrated.migrator_engine(),
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema IN ('raw', 'quarantine', 'ingest', 'prep') AND table_type = 'BASE TABLE'",
            )
        }

        assert tables == {
            "raw.event",
            "quarantine.event",
            "quarantine.error_code",
            "ingest.event_source",
            "ingest.event_type",
            "ingest.audit_action",
            "ingest.project_key_table",
            "ingest.ingest_batch",
            "ingest.ingest_audit",
            "ingest.ingest_audit_table",
        }

    def test_json_columns_exist_only_in_raw_and_quarantine(self, migrated: PostgresInstance) -> None:
        columns = rows(
            migrated.migrator_engine(),
            "SELECT table_schema || '.' || table_name FROM information_schema.columns "
            "WHERE table_schema IN ('raw', 'quarantine', 'ingest') AND data_type IN ('json', 'jsonb') ORDER BY 1",
        )

        assert sorted(set(columns)) == [("quarantine.event",), ("raw.event",)]

    def test_the_code_lists_equal_what_the_code_knows(self, migrated: PostgresInstance) -> None:
        engine = migrated.migrator_engine()

        assert dict(rows(engine, "SELECT code, source_code FROM ingest.event_type")) == {
            name: source.value for name, source in SOURCE_BY_EVENT_TYPE.items()
        }
        assert {code for (code,) in rows(engine, "SELECT code FROM ingest.event_source")} == {
            source.value for source in SOURCE_BY_EVENT_TYPE.values()
        }
        assert {code for (code,) in rows(engine, "SELECT code FROM quarantine.error_code")} == {
            reason.value for reason in QuarantineReason
        }
        assert {code for (code,) in rows(engine, "SELECT code FROM ingest.project_key_table")} == {
            table.qualified for table in StaticProjectKeyTableRegistry().tables()
        }
        assert rows(engine, "SELECT code FROM ingest.audit_action") == [("PROJECT_DATA_DELETED",)]

    def test_running_the_migrations_again_changes_nothing(self, migrated: PostgresInstance) -> None:
        before = rows(migrated.migrator_engine(), "SELECT version_num FROM alembic_version")

        apply_migrations(migrated.settings(), MIGRATIONS_DIR)

        assert rows(migrated.migrator_engine(), "SELECT version_num FROM alembic_version") == before == [("0001",)]


class TestConstraints:
    @pytest.fixture
    def engine(self, migrated: PostgresInstance) -> Engine:
        return migrated.migrator_engine()

    def test_an_event_needs_a_valid_project_key_version_and_object_payload(
        self, migrated: PostgresInstance, engine: Engine
    ) -> None:
        batch_id = seed_batch(migrated)
        for override, constraint in (
            ({"key": "A" * 64}, "ck_event_project_key"),
            ({"key": "a" * 63}, "ck_event_project_key"),
            ({"version": 0}, "ck_event_schema_version"),
            ({"payload": "[]"}, "ck_event_payload_object"),
        ):
            sql, params = event_insert(**override)
            refused(engine, sql, constraint, batch_id=batch_id, **params)

    def test_the_source_must_belong_to_the_event_type(self, migrated: PostgresInstance, engine: Engine) -> None:
        sql, params = event_insert(source="agent-service", event_type="finding_detected")
        refused(engine, sql, "fk_event_event_type_source", batch_id=seed_batch(migrated), **params)

    def test_an_unknown_event_type_or_batch_is_refused(self, migrated: PostgresInstance, engine: Engine) -> None:
        sql, params = event_insert(event_type="made_up")
        refused(engine, sql, "fk_event_event_type_source", batch_id=seed_batch(migrated), **params)
        sql, params = event_insert()
        refused(engine, sql, "fk_event_batch", batch_id=uuid.uuid4(), **params)

    def test_a_revocation_is_a_command_and_is_never_stored_as_an_event(
        self, migrated: PostgresInstance, engine: Engine
    ) -> None:
        sql, params = event_insert(event_type="consent_revoked")
        refused(engine, sql, "ck_event_not_a_command", batch_id=seed_batch(migrated), **params)

    def test_an_event_id_is_stored_once(self, migrated: PostgresInstance, engine: Engine) -> None:
        batch_id = seed_batch(migrated)
        sql, params = event_insert()
        rows(engine, sql, batch_id=batch_id, **params)

        refused(engine, sql, "pk_event", batch_id=batch_id, **params)

    def test_a_batch_has_between_1_and_500_events_and_at_most_that_many_duplicates(self, engine: Engine) -> None:
        for received, duplicate, constraint in (
            (0, 0, "ck_ingest_batch_received_count"),
            (501, 0, "ck_ingest_batch_received_count"),
            (2, 3, "ck_ingest_batch_duplicate_count"),
        ):
            refused(
                engine,
                "INSERT INTO ingest.ingest_batch (id, received_at, received_count, duplicate_count) "
                "VALUES (:id, :now, :received, :duplicate)",
                constraint,
                id=uuid.uuid4(),
                now=NOW,
                received=received,
                duplicate=duplicate,
            )

    def test_a_quarantined_record_is_stored_once_and_needs_a_known_reason(
        self, migrated: PostgresInstance, engine: Engine
    ) -> None:
        batch_id = seed_batch(migrated, received=2)
        sql = (
            "INSERT INTO quarantine.event (id, batch_id, record_sha256, record, error_code, error_message, quarantined_at) "
            "VALUES (:id, :batch_id, :sha, CAST('{}' AS jsonb), :code, 'x', :now)"
        )
        sha = "c" * 64
        rows(engine, sql, id=uuid.uuid4(), batch_id=batch_id, sha=sha, code="schema-violation", now=NOW)

        refused(
            engine,
            sql,
            "uq_quarantine_event_record",
            id=uuid.uuid4(),
            batch_id=batch_id,
            sha=sha,
            code="schema-violation",
            now=NOW,
        )
        refused(
            engine,
            sql,
            "fk_quarantine_event_error_code",
            id=uuid.uuid4(),
            batch_id=batch_id,
            sha="d" * 64,
            code="nope",
            now=NOW,
        )
        refused(
            engine,
            sql,
            "ck_quarantine_event_sha256",
            id=uuid.uuid4(),
            batch_id=batch_id,
            sha="not-a-hash",
            code="schema-violation",
            now=NOW,
        )

    def test_a_quarantined_project_key_is_valid_or_absent(self, migrated: PostgresInstance, engine: Engine) -> None:
        refused(
            engine,
            "INSERT INTO quarantine.event (id, batch_id, project_key, record_sha256, record, error_code, error_message, "
            "quarantined_at) VALUES (:id, :batch_id, 'short', :sha, CAST('{}' AS jsonb), 'schema-violation', 'x', :now)",
            "ck_quarantine_event_project_key",
            id=uuid.uuid4(),
            batch_id=seed_batch(migrated),
            sha="e" * 64,
            now=NOW,
        )

    def test_an_erasure_is_audited_once_per_event_and_only_for_registered_tables(
        self, migrated: PostgresInstance, engine: Engine
    ) -> None:
        audit = uuid.uuid4()
        event = uuid.uuid4()
        insert = (
            "INSERT INTO ingest.ingest_audit (id, performed_at, action_code, project_key, event_id, revoked_at) "
            "VALUES (:id, :now, :action, :key, :event, :now)"
        )
        rows(engine, insert, id=audit, now=NOW, action="PROJECT_DATA_DELETED", key=KEY_A, event=event)

        refused(
            engine,
            insert,
            "uq_ingest_audit_event",
            id=uuid.uuid4(),
            now=NOW,
            action="PROJECT_DATA_DELETED",
            key=KEY_A,
            event=event,
        )
        refused(
            engine,
            insert,
            "fk_ingest_audit_action",
            id=uuid.uuid4(),
            now=NOW,
            action="OTHER",
            key=KEY_A,
            event=uuid.uuid4(),
        )
        detail = "INSERT INTO ingest.ingest_audit_table (audit_id, table_name, deleted_rows) VALUES (:id, :table, :n)"
        refused(engine, detail, "fk_ingest_audit_table_name", id=audit, table="public.secrets", n=1)
        refused(engine, detail, "ck_ingest_audit_table_deleted_rows", id=audit, table="raw.event", n=-1)
        rows(engine, detail, id=audit, table="raw.event", n=3)
        refused(engine, detail, "pk_ingest_audit_table", id=audit, table="raw.event", n=3)


class TestPrivileges:
    def test_the_application_role_cannot_change_the_schema(self, migrated: PostgresInstance) -> None:
        app = migrated.app_engine()

        refused(app, "CREATE TABLE raw.extra (id int)", "permission denied")
        refused(app, "CREATE SCHEMA extra", "permission denied")
        refused(app, "CREATE TEMP TABLE scratch (id int)", "permission denied")
        refused(app, "DROP TABLE raw.event", "must be owner")

    def test_the_application_role_reads_the_code_lists_but_never_changes_them(self, migrated: PostgresInstance) -> None:
        app = migrated.app_engine()

        assert rows(app, "SELECT count(*) FROM ingest.event_type") == [(len(SOURCE_BY_EVENT_TYPE),)]
        refused(
            app,
            "INSERT INTO ingest.event_type (code, source_code, description, sort_order) VALUES ('x', 'core-service', 'x', 9)",
            "permission denied",
        )
        refused(app, "DELETE FROM ingest.event_type", "permission denied")
        refused(app, "UPDATE quarantine.error_code SET description = 'x'", "permission denied")

    def test_an_event_is_written_once_and_erased_never_updated_or_truncated(self, migrated: PostgresInstance) -> None:
        batch_id = seed_batch(migrated)
        app = migrated.app_engine()
        sql, params = event_insert()
        rows(app, sql, batch_id=batch_id, **params)

        refused(app, "UPDATE raw.event SET payload = CAST('{}' AS jsonb)", "permission denied")
        refused(app, "TRUNCATE raw.event", "permission denied")
        rows(app, "DELETE FROM raw.event WHERE project_key = :key", key=KEY_A)

    def test_a_batch_may_only_have_its_duplicate_count_updated(self, migrated: PostgresInstance) -> None:
        batch_id = seed_batch(migrated, received=2)
        app = migrated.app_engine()

        rows(app, "UPDATE ingest.ingest_batch SET duplicate_count = 1 WHERE id = :id", id=batch_id)
        refused(
            app, "UPDATE ingest.ingest_batch SET received_count = 1 WHERE id = :id", "permission denied", id=batch_id
        )
        refused(app, "DELETE FROM ingest.ingest_batch", "permission denied")

    def test_the_audit_is_append_only_for_the_application_role(self, migrated: PostgresInstance) -> None:
        app = migrated.app_engine()

        refused(app, "UPDATE ingest.ingest_audit SET project_key = :key", "permission denied", key=KEY_A)
        refused(app, "DELETE FROM ingest.ingest_audit", "permission denied")
        refused(app, "DELETE FROM ingest.ingest_audit_table", "permission denied")

    def test_the_read_only_role_sees_nothing_of_the_landing_layer(self, migrated: PostgresInstance) -> None:
        reader = migrated.reader_engine()

        refused(reader, "SELECT 1 FROM raw.event", "permission denied")
        refused(reader, "SELECT 1 FROM quarantine.event", "permission denied")
        refused(reader, "SELECT 1 FROM ingest.ingest_audit", "permission denied")


class TestReviewFindings:
    def test_the_time_a_row_repeats_from_its_batch_must_be_the_batch_time(self, migrated: PostgresInstance) -> None:
        engine = migrated.migrator_engine()
        batch_id = seed_batch(migrated)
        sql, params = event_insert()
        # received_at and quarantined_at are copies of the batch's received_at: the composite foreign key keeps them equal.
        mismatch = sql.replace(":now, :now, :key", ":now, '2026-10-28T00:00:00Z', :key")
        refused(engine, mismatch, "fk_event_batch", batch_id=batch_id, **params)
        refused(
            engine,
            "INSERT INTO quarantine.event (id, batch_id, record_sha256, record, error_code, error_message, quarantined_at) "
            "VALUES (:id, :batch_id, :sha, CAST('{}' AS jsonb), 'schema-violation', 'x', '2026-10-28T00:00:00Z')",
            "fk_quarantine_event_batch",
            id=uuid.uuid4(),
            batch_id=batch_id,
            sha="f" * 64,
        )

    def test_a_revocation_is_audited_with_the_time_it_cuts_off(self, migrated: PostgresInstance) -> None:
        refused(
            migrated.migrator_engine(),
            "INSERT INTO ingest.ingest_audit (id, performed_at, action_code, project_key, event_id) "
            "VALUES (:id, :now, 'PROJECT_DATA_DELETED', :key, :event)",
            "revoked_at",
            id=uuid.uuid4(),
            now=NOW,
            key=KEY_A,
            event=uuid.uuid4(),
        )

    def test_the_application_role_cannot_touch_the_schema_version_table(self, migrated: PostgresInstance) -> None:
        app = migrated.app_engine()

        refused(app, "UPDATE public.alembic_version SET version_num = '0002'", "permission denied")
        refused(app, "DELETE FROM public.alembic_version", "permission denied")

    def test_more_things_the_application_role_may_not_do(self, migrated: PostgresInstance) -> None:
        app = migrated.app_engine()

        refused(app, "UPDATE quarantine.event SET error_message = 'x'", "permission denied")
        refused(app, "TRUNCATE quarantine.event", "permission denied")
        refused(app, "UPDATE ingest.ingest_audit_table SET deleted_rows = 0", "permission denied")
        refused(app, "TRUNCATE ingest.ingest_batch", "permission denied")
        refused(app, "UPDATE ingest.ingest_audit SET revoked_at = now()", "permission denied")

    def test_every_table_that_holds_a_project_key_is_in_the_erasure_registry_or_is_the_audit(
        self, migrated: PostgresInstance
    ) -> None:
        holders = {
            f"{schema}.{name}"
            for schema, name in rows(
                migrated.migrator_engine(),
                "SELECT table_schema, table_name FROM information_schema.columns "
                "WHERE column_name = 'project_key' AND table_schema IN ('raw', 'quarantine', 'ingest', 'prep', 'public')",
            )
        }

        registered = {table.qualified for table in StaticProjectKeyTableRegistry().tables()}

        # The audit keeps the key on purpose (D-127: the HMAC key and the action, nothing else); everything else is erased.
        # A table a later phase adds (prep.*, a warehouse table) fails this test until it is registered.
        assert holders - {"ingest.ingest_audit"} == registered
