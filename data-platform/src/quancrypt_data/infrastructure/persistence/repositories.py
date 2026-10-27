"""PostgreSQL adapters of the outbound ports (SQLAlchemy Core, parametrised SQL; D-08). Every one of them works in the
transaction `Database.run` opened; none opens its own."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from quancrypt_data.domain.events import Event, EventSource, ProjectKeyTable
from quancrypt_data.infrastructure.persistence.database import Database
from quancrypt_data.port.outbound.erasure import ErasureRecord, ProjectKeyTableRegistry
from quancrypt_data.port.outbound.storage import QuarantineEntry

_LOCK_NAMESPACE = "quancrypt-ingest:"
# What a project-key erasure covers in P6.1; P6.4 (prep) and P6.6 (warehouse) extend the list (D-295d).
_REGISTERED_TABLES = (ProjectKeyTable("raw", "event"), ProjectKeyTable("quarantine", "event"))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


class PostgresBatchStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def start(self, batch_id: UUID, received_at: datetime, received_count: int) -> None:
        self._database.connection().execute(
            text(
                "INSERT INTO ingest.ingest_batch (id, received_at, received_count, duplicate_count) "
                "VALUES (:id, :received_at, :received_count, 0)"
            ),
            {"id": batch_id, "received_at": received_at, "received_count": received_count},
        )

    def finish(self, batch_id: UUID, duplicate_count: int) -> None:
        self._database.connection().execute(
            text("UPDATE ingest.ingest_batch SET duplicate_count = :duplicate_count WHERE id = :id"),
            {"id": batch_id, "duplicate_count": duplicate_count},
        )


class PostgresEventStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def insert_if_absent(self, event: Event, source: EventSource, batch_id: UUID, received_at: datetime) -> bool:
        result = self._database.connection().execute(
            text(
                "INSERT INTO raw.event (event_id, batch_id, source, source_ref, event_type, schema_version, "
                "occurred_at, received_at, project_key, payload) "
                "VALUES (:event_id, :batch_id, :source, NULL, :event_type, :schema_version, :occurred_at, "
                ":received_at, :project_key, CAST(:payload AS jsonb)) "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "event_id": event.event_id,
                "batch_id": batch_id,
                "source": source.value,
                "event_type": event.event_type,
                "schema_version": event.schema_version,
                "occurred_at": event.occurred_at,
                "received_at": received_at,
                "project_key": event.project_key,
                "payload": _json(event.payload),
            },
        )
        return result.rowcount == 1


class PostgresQuarantineStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def insert_if_absent(self, entry: QuarantineEntry) -> bool:
        result = self._database.connection().execute(
            text(
                "INSERT INTO quarantine.event (id, batch_id, event_id, project_key, record_sha256, record, error_code, "
                "error_message, quarantined_at) "
                "VALUES (:id, :batch_id, :event_id, :project_key, :record_sha256, CAST(:record AS jsonb), :error_code, "
                ":error_message, :quarantined_at) "
                "ON CONFLICT (record_sha256) DO NOTHING"
            ),
            {
                "id": entry.id,
                "batch_id": entry.batch_id,
                "event_id": entry.event_id,
                "project_key": entry.project_key,
                "record_sha256": entry.record_sha256,
                "record": _json(entry.record),
                "error_code": entry.reason.value,
                "error_message": entry.message,
                "quarantined_at": entry.quarantined_at,
            },
        )
        return result.rowcount == 1


class StaticProjectKeyTableRegistry:
    def tables(self) -> Sequence[ProjectKeyTable]:
        return _REGISTERED_TABLES


class PostgresProjectDataEraser:
    def __init__(self, database: Database, registry: ProjectKeyTableRegistry) -> None:
        self._database = database
        self._registry = registry

    def delete(self, table: ProjectKeyTable, project_key: str) -> int:
        if table not in self._registry.tables():
            raise ValueError("the table is not in the project-key registry")
        # The identifiers are fixed constants checked against [a-z_]+ (ProjectKeyTable); the key is bound.
        result = self._database.connection().execute(
            text(f"DELETE FROM {table.qualified} WHERE project_key = :project_key"), {"project_key": project_key}
        )
        return result.rowcount


class PostgresErasureAudit:
    def __init__(self, database: Database) -> None:
        self._database = database

    def latest_revocation(self, project_key: str) -> datetime | None:
        latest = (
            self._database.connection()
            .execute(
                text("SELECT max(revoked_at) FROM ingest.ingest_audit WHERE project_key = :project_key"),
                {"project_key": project_key},
            )
            .scalar_one()
        )
        return latest if isinstance(latest, datetime) else None

    def is_recorded(self, event_id: UUID) -> bool:
        row = self._database.connection().execute(
            text("SELECT 1 FROM ingest.ingest_audit WHERE event_id = :event_id"), {"event_id": event_id}
        )
        return row.first() is not None

    def record(self, record: ErasureRecord) -> None:
        connection = self._database.connection()
        connection.execute(
            text(
                "INSERT INTO ingest.ingest_audit (id, performed_at, action_code, project_key, event_id, revoked_at) "
                "VALUES (:id, :performed_at, 'PROJECT_DATA_DELETED', :project_key, :event_id, :revoked_at)"
            ),
            {
                "id": record.id,
                "performed_at": record.performed_at,
                "project_key": record.project_key,
                "event_id": record.event_id,
                "revoked_at": record.revoked_at,
            },
        )
        for table_name, deleted_rows in sorted(record.deleted.items()):
            connection.execute(
                text(
                    "INSERT INTO ingest.ingest_audit_table (audit_id, table_name, deleted_rows) "
                    "VALUES (:audit_id, :table_name, :deleted_rows)"
                ),
                {"audit_id": record.id, "table_name": table_name, "deleted_rows": deleted_rows},
            )


class PostgresProjectKeyLock:
    def __init__(self, database: Database) -> None:
        self._database = database

    def acquire(self, project_keys: Sequence[str]) -> None:
        connection = self._database.connection()
        # Sorted, so two transactions that lock several keys take them in the same order (no deadlock).
        for key in sorted(set(project_keys)):
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": _LOCK_NAMESPACE + key}
            )
