"""PostgreSQL adapters of the preprocessing ports (P6.4): `RawEventSource` reads raw in a READ ONLY transaction;
`PostgresPrepRepository` writes one project per transaction (delete, then insert: idempotent); `PostgresPrepReader`
reads prep back for the leak check and the report. Every statement is fixed text with bound values."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import text

from quancrypt_data.domain.prep import LabelRow, RawEvent, RawLabel, Rejection
from quancrypt_data.infrastructure.persistence.database import Database
from quancrypt_data.infrastructure.persistence.repositories import LOCK_NAMESPACE
from quancrypt_data.port.outbound.prep import ProjectContent, TableStat
from quancrypt_data.port.outbound.system import Clock

_REJECTION_NAMESPACE = uuid.UUID("8f4a2b6c-1d3e-4f70-9a85-2c6b7d9e0f13")

# The prep tables and their columns the leak check reads (text) and the report profiles (all).
PREP_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "prep.project_snapshot": ("project_key", "origin", "is_outlier_project"),
    "prep.analysis_unit": ("unit_path", "java_version", "spring_boot_version"),
    "prep.finding": (
        "unit_path", "file_path", "line_start", "line_end", "algorithm_family", "usage_context", "location_kind",
        "priority", "key_size_bits", "key_size_known", "mode", "padding", "hash", "library", "confidence",
        "in_test_code",
    ),
    "prep.topology_summary": ("unit_path", "node_count", "edge_count", "tls_edge_count", "mtls_edge_count"),
    "prep.service_link": ("unit_path", "protocol", "tls", "mtls"),
    "prep.scope_decision": ("decision", "confidence", "deciding_ring", "latency_ms", "language"),
    "prep.benchmark_label": ("case_id", "file_path", "category", "cwe", "expected_vulnerable"),
}  # fmt: skip
TEXT_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "prep.analysis_unit": ("unit_path", "java_version", "spring_boot_version"),
    "prep.finding": ("unit_path", "file_path", "mode", "padding", "hash", "library"),
    "prep.topology_summary": ("unit_path",),
    "prep.service_link": ("unit_path",),
    "prep.benchmark_label": ("case_id", "file_path", "category"),
}

# The columns that hold a path: anonymised segments joined by "/" (D-308b).
PATH_COLUMNS = frozenset({"unit_path", "file_path"})


class PostgresRawEventSource:
    def __init__(self, database: Database) -> None:
        self._database = database

    def _read_only[T](self, work: Callable[[], T]) -> T:
        def guarded() -> T:
            self._database.connection().execute(text("SET TRANSACTION READ ONLY"))
            return work()

        return self._database.run(guarded)

    def events(self) -> Sequence[RawEvent]:
        def work() -> list[RawEvent]:
            rows = self._database.connection().execute(
                text(
                    "SELECT event_id, event_type, source, schema_version, occurred_at, project_key, payload "
                    "FROM raw.event ORDER BY event_id"
                )
            )
            return [
                RawEvent(
                    str(r.event_id), r.event_type, r.source, int(r.schema_version), r.occurred_at, r.project_key,
                    r.payload if isinstance(r.payload, dict) else {},
                )
                for r in rows
            ]  # fmt: skip

        return self._read_only(work)

    def labels(self) -> Sequence[RawLabel]:
        def work() -> list[RawLabel]:
            rows = self._database.connection().execute(
                text(
                    "SELECT benchmark, case_id, file_path, category, cwe, expected_vulnerable FROM raw.benchmark_label "
                    "ORDER BY benchmark, case_id"
                )
            )
            return [
                RawLabel(r.benchmark, r.case_id, r.file_path, r.category, r.cwe, r.expected_vulnerable) for r in rows
            ]

        return self._read_only(work)


def _rejection_rows(rejected: Sequence[Rejection], quarantined_at: object) -> list[dict[str, Any]]:
    rows = []
    for position, r in enumerate(rejected):
        subject = r.raw_event_id or (f"{r.label[0]}/{r.label[1]}" if r.label else "")
        rows.append(
            {
                "id": uuid.uuid5(_REJECTION_NAMESPACE, f"{r.filter_code}:{subject}:{r.message}:{position}"),
                "project_key": r.project_key if r.label is None else None,
                "raw_event_id": r.raw_event_id,
                "benchmark": r.label[0] if r.label else None,
                "case_id": r.label[1] if r.label else None,
                "filter_code": r.filter_code,
                "error_code": r.error_code,
                "error_message": r.message[:500],
                "rows_set_aside": r.rows,
                "quarantined_at": quarantined_at,
            }
        )
    return rows


_INSERT_REJECTION = text(
    "INSERT INTO quarantine.prep_record (id, project_key, raw_event_id, benchmark, case_id, filter_code, error_code, "
    "error_message, rows_set_aside, quarantined_at) VALUES (:id, :project_key, :raw_event_id, :benchmark, :case_id, "
    ":filter_code, :error_code, :error_message, :rows_set_aside, :quarantined_at)"
)


class PostgresPrepRepository:
    def __init__(self, database: Database, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    def stored_project_keys(self) -> set[str]:
        def work() -> set[str]:
            rows = self._database.connection().execute(
                text(
                    "SELECT project_key FROM prep.project_snapshot UNION "
                    "SELECT project_key FROM quarantine.prep_record WHERE project_key IS NOT NULL"
                )
            )
            return {r.project_key for r in rows}

        return self._database.run(work)

    def replace_project(self, project_key: str, content: ProjectContent | None, rejected: Sequence[Rejection]) -> None:
        def work() -> None:
            connection = self._database.connection()
            key = {"project_key": project_key}
            # The lock of the erasure (ingest-api takes it before it deletes a project key): a consent revocation either
            # finished before this transaction (raw has no event of the key: nothing is written) or waits for it and
            # then deletes what was written. Without it the pipeline wrote a revoked project back from its earlier read.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": LOCK_NAMESPACE + project_key}
            )
            # Only rows whose source event is still in raw are written: a revocation followed by a new event of the
            # same key must not bring back what the revocation deleted (D-315).
            wanted = _source_event_ids(content, rejected)
            alive = (
                {
                    str(r[0])
                    for r in connection.execute(
                        text(
                            "SELECT event_id FROM raw.event WHERE project_key = :project_key AND event_id = ANY(:ids)"
                        ),
                        {**key, "ids": [uuid.UUID(i) for i in sorted(wanted)]},
                    )
                }
                if wanted
                else set()
            )
            still_in_raw = bool(alive) or (
                not wanted
                and connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM raw.event WHERE project_key = :project_key)"), key
                ).scalar_one()
            )
            kept = _only_events(content, alive) if content is not None else None
            kept_rejections = [r for r in rejected if r.raw_event_id is None or r.raw_event_id in alive]
            # The snapshot's rows go with it (ON DELETE CASCADE); the quarantine rows are the key's own.
            connection.execute(text("DELETE FROM prep.project_snapshot WHERE project_key = :project_key"), key)
            connection.execute(text("DELETE FROM quarantine.prep_record WHERE project_key = :project_key"), key)
            if not still_in_raw:
                return
            if kept is not None:
                self._insert(kept)
            if kept_rejections:
                connection.execute(_INSERT_REJECTION, _rejection_rows(kept_rejections, self._clock.now()))

        self._database.run(work)

    def _insert(self, content: ProjectContent) -> None:
        connection = self._database.connection()
        p = content.project
        connection.execute(
            text(
                "INSERT INTO prep.project_snapshot (project_key, origin, is_outlier_project) "
                "VALUES (:project_key, :origin, :is_outlier_project)"
            ),
            {"project_key": p.project_key, "origin": p.origin, "is_outlier_project": p.is_outlier_project},
        )
        if content.units:
            connection.execute(
                text(
                    "INSERT INTO prep.analysis_unit (project_key, unit_path, java_version, spring_boot_version, "
                    "analysed_at) VALUES (:project_key, :unit_path, :java_version, :spring_boot_version, :analysed_at)"
                ),
                [vars(u) for u in content.units],
            )
        if content.findings:
            connection.execute(
                text(
                    "INSERT INTO prep.finding (id, project_key, unit_path, source_event_id, file_path, line_start, "
                    "line_end, algorithm_family, usage_context, location_kind, priority, key_size_bits, mode, padding, "
                    "hash, library, confidence, in_test_code) VALUES (:id, :project_key, :unit_path, :source_event_id, "
                    ":file_path, :line_start, :line_end, :algorithm_family, :usage_context, :location_kind, :priority, "
                    ":key_size_bits, :mode, :padding, :hash, :library, :confidence, :in_test_code)"
                ),
                [vars(f) for f in content.findings],
            )
        if content.topologies:
            connection.execute(
                text(
                    "INSERT INTO prep.topology_summary (project_key, unit_path, source_event_id, node_count, "
                    "edge_count, "
                    "tls_edge_count, mtls_edge_count, recorded_at) VALUES (:project_key, :unit_path, :source_event_id, "
                    ":node_count, :edge_count, :tls_edge_count, :mtls_edge_count, :recorded_at)"
                ),
                [vars(t) for t in content.topologies],
            )
        if content.links:
            connection.execute(
                text(
                    "INSERT INTO prep.service_link (project_key, unit_path, ordinal, protocol, tls, mtls) "
                    "VALUES (:project_key, :unit_path, :ordinal, :protocol, :tls, :mtls)"
                ),
                [vars(link) for link in content.links],
            )
        if content.scopes:
            connection.execute(
                text(
                    "INSERT INTO prep.scope_decision (event_id, project_key, occurred_at, decision, confidence, "
                    "deciding_ring, latency_ms, language) VALUES (:event_id, :project_key, :occurred_at, :decision, "
                    ":confidence, :deciding_ring, :latency_ms, :language)"
                ),
                [vars(s) for s in content.scopes],
            )

    def replace_labels(self, labels: Sequence[LabelRow], rejected: Sequence[Rejection]) -> None:
        def work() -> None:
            connection = self._database.connection()
            connection.execute(text("DELETE FROM prep.benchmark_label"))
            connection.execute(text("DELETE FROM quarantine.prep_record WHERE project_key IS NULL"))
            if labels:
                connection.execute(
                    text(
                        "INSERT INTO prep.benchmark_label (benchmark, case_id, file_path, category, cwe, "
                        "expected_vulnerable) VALUES (:benchmark, :case_id, :file_path, :category, :cwe, "
                        ":expected_vulnerable)"
                    ),
                    [vars(label) for label in labels],
                )
            if rejected:
                connection.execute(_INSERT_REJECTION, _rejection_rows(rejected, self._clock.now()))

        self._database.run(work)


class PostgresPrepReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    def text_values(self) -> Sequence[str]:
        return self._values(TEXT_COLUMNS)

    def path_values(self) -> Sequence[str]:
        return self._values({t: tuple(c for c in cols if c in PATH_COLUMNS) for t, cols in TEXT_COLUMNS.items()})

    def _values(self, selection: Mapping[str, tuple[str, ...]]) -> Sequence[str]:
        def work() -> list[str]:
            connection = self._database.connection()
            values: list[str] = []
            for table, columns in selection.items():
                for column in columns:
                    # Table and column names are the constants above; nothing of the data is in the statement.
                    rows = connection.execute(text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"))  # noqa: S608
                    values.extend(str(r[0]) for r in rows)
            return values

        return self._database.run(work)

    def table_stats(self) -> Sequence[TableStat]:
        def work() -> list[TableStat]:
            connection = self._database.connection()
            stats = []
            for table, columns in PREP_COLUMNS.items():
                nulls = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL)" for c in columns)
                row = connection.execute(text(f"SELECT count(*), {nulls} FROM {table}")).one()  # noqa: S608
                total = int(row[0])
                ratios = {c: (int(row[i + 1]) / total if total else 0.0) for i, c in enumerate(columns)}
                stats.append(TableStat(table, total, ratios))
            return stats

        return self._database.run(work)


def _source_event_ids(content: ProjectContent | None, rejected: Sequence[Rejection]) -> set[str]:
    ids = {r.raw_event_id for r in rejected if r.raw_event_id}
    if content is not None:
        ids |= {f.source_event_id for f in content.findings} | {t.source_event_id for t in content.topologies}
        ids |= {link.source_event_id for link in content.links} | {s.event_id for s in content.scopes}
    return ids


def _only_events(content: ProjectContent, alive: set[str]) -> ProjectContent:
    """The content without the rows whose source event is gone from raw."""
    return replace(
        content,
        findings=tuple(f for f in content.findings if f.source_event_id in alive),
        topologies=tuple(t for t in content.topologies if t.source_event_id in alive),
        links=tuple(link for link in content.links if link.source_event_id in alive),
        scopes=tuple(s for s in content.scopes if s.event_id in alive),
    )
