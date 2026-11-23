"""PostgreSQL adapter of `RawDataReader` (P6.3): reads raw.event, raw.benchmark_label and quarantine.event, every
query in a READ ONLY transaction, so the database itself refuses a write (D-302c). Payloads are parsed here; a
payload that does not have the expected shape is skipped (raw holds only schema-valid events, the quarantine holds
the rest)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import text

from quancrypt_data.domain.events import SOURCE_BY_EVENT_TYPE
from quancrypt_data.domain.profiling import (
    FindingRecord,
    LabelRecord,
    QuarantineRecord,
    RawSnapshot,
    RuntimeRecord,
    ScopeRecord,
    SourceSummary,
    TableChecksum,
    TextSample,
    TopologyRecord,
)
from quancrypt_data.infrastructure.persistence.database import Database

# Whole-row digests in key order: the md5 of each row's text (`row::text` holds every column, tells NULL from an
# empty value and writes jsonb canonically), then the md5 of that list. Equal count and digest = equal rows, so a
# change to any column of any row shows; both sides are read in one process, so the time zone of timestamps is the same.
CHECKSUMS = tuple(
    (table, f"SELECT count(*), md5(coalesce(string_agg(md5(t::text), ',' ORDER BY {order}), '')) FROM {table} t")
    for table, order in (
        ("raw.event", "t.event_id"),
        ("quarantine.event", "t.id"),
        ("raw.benchmark_label", "t.benchmark, t.case_id"),
        ("raw.benchmark_load", "t.benchmark"),
    )
)


def _project_path(unit: str | None, file: str | None) -> str | None:
    if file is None or unit is None or unit == ".":
        return file
    return f"{unit.rstrip('/')}/{file}"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


class PostgresRawDataReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    def _read_only[T](self, work: Callable[[], T]) -> T:
        def guarded() -> T:
            self._database.connection().execute(text("SET TRANSACTION READ ONLY"))
            return work()

        return self._database.run(guarded)

    def checksums(self) -> Sequence[TableChecksum]:
        def work() -> list[TableChecksum]:
            connection = self._database.connection()
            result = []
            for table, sql in CHECKSUMS:
                rows, digest = connection.execute(text(sql)).one()
                result.append(TableChecksum(table, int(rows), str(digest)))
            return result

        return self._read_only(work)

    def snapshot(self) -> RawSnapshot:
        return self._read_only(self._snapshot)

    def _snapshot(self) -> RawSnapshot:
        connection = self._database.connection()
        sources = tuple(
            SourceSummary(
                source=row.source,
                event_type=row.event_type,
                count=int(row.n),
                first_at=row.first_at,
                last_at=row.last_at,
                schema_versions=tuple(sorted(row.versions)),
            )
            for row in connection.execute(
                text(
                    "SELECT source, event_type, count(*) AS n, min(occurred_at) AS first_at, "
                    "max(occurred_at) AS last_at, "
                    "array_agg(DISTINCT schema_version) AS versions FROM raw.event GROUP BY source, event_type "
                    "ORDER BY source, event_type"
                )
            )
        )
        findings: list[FindingRecord] = []
        topologies: list[TopologyRecord] = []
        runtimes: list[RuntimeRecord] = []
        scopes: list[ScopeRecord] = []
        texts: list[TextSample] = []
        project_keys: set[str] = set()
        for row in connection.execute(text("SELECT event_type, project_key, payload FROM raw.event ORDER BY event_id")):
            project_keys.add(row.project_key)
            payload: Mapping[str, Any] = row.payload if isinstance(row.payload, dict) else {}
            source = SOURCE_BY_EVENT_TYPE.get(row.event_type)
            source_name = source.value if source is not None else "unknown"
            if row.event_type in ("corpus_analysis", "benchmark_analysis"):
                self._analysis(source_name, row.project_key, payload, findings, topologies, runtimes, texts)
            elif row.event_type == "finding_detected":
                findings.append(self._coded_finding(source_name, row.project_key, payload))
            elif row.event_type == "topology_recorded":
                topologies.append(
                    TopologyRecord(
                        source_name, row.project_key, _int(payload.get("node_count")) or 0,
                        _int(payload.get("link_count")) or 0, None, None,
                    )
                )  # fmt: skip
            elif row.event_type == "project_runtime_changed" and isinstance(payload.get("current"), dict):
                current = payload["current"]
                runtimes.append(
                    RuntimeRecord(
                        source_name, row.project_key, _text(current.get("java_version")),
                        _text(current.get("spring_boot_version")),
                    )
                )  # fmt: skip
            elif row.event_type == "scope_decision":
                scopes.append(
                    ScopeRecord(
                        str(payload.get("decision")), str(payload.get("deciding_ring")),
                        _float(payload.get("confidence")),
                        _int(payload.get("latency_ms")) or 0, str(payload.get("language")),
                    )
                )  # fmt: skip
        labels = tuple(
            LabelRecord(r.benchmark, r.case_id, r.file_path, r.category, r.cwe, r.expected_vulnerable)
            for r in connection.execute(
                text(
                    "SELECT benchmark, case_id, file_path, category, cwe, expected_vulnerable FROM raw.benchmark_label "
                    "ORDER BY benchmark, case_id"
                )
            )
        )
        quarantine = []
        for r in connection.execute(
            text("SELECT error_code, error_message, record::text AS record FROM quarantine.event ORDER BY id")
        ):
            quarantine.append(QuarantineRecord(r.error_code, r.error_message))
            texts.append(TextSample("quarantine.record", r.record))
        return RawSnapshot(
            sources=sources,
            findings=tuple(findings),
            topologies=tuple(topologies),
            runtimes=tuple(runtimes),
            scopes=tuple(scopes),
            labels=labels,
            quarantine=tuple(quarantine),
            texts=tuple(texts),
            project_keys=frozenset(project_keys),
        )

    @staticmethod
    def _analysis(
        source: str,
        key: str,
        payload: Mapping[str, Any],
        findings: list[FindingRecord],
        topologies: list[TopologyRecord],
        runtimes: list[RuntimeRecord],
        texts: list[TextSample],
    ) -> None:
        # A finding's path is relative to its analysis unit (a service directory when the repository root is not one
        # build, D-298b); the unit is put in front, or the same relative path in two services would look like one file.
        unit = _text(payload.get("analysis_unit"))
        for item in payload.get("findings") or []:
            if not isinstance(item, dict):
                continue
            finding = FindingRecord(
                source=source,
                project_key=key,
                algorithm_family=str(item.get("algorithm_family")),
                usage_context=str(item.get("usage_context")),
                location_kind=str(item.get("location_kind")),
                priority=str(item.get("priority")),
                key_size_bits=_int(item.get("key_size_bits")),
                confidence=_float(item.get("confidence")),
                file=_project_path(unit, _text(item.get("file"))),
                line_start=_int(item.get("line_start")),
                raw_name=_text(item.get("raw_name")),
                mode=_text(item.get("mode")),
                padding=_text(item.get("padding")),
                hash=_text(item.get("hash")),
                library=_text(item.get("library")),
            )
            findings.append(finding)
            texts.extend(
                TextSample(f"findings.{name}", value)
                for name in ("file", "raw_name")
                if (value := getattr(finding, name))
            )
        topology = payload.get("topology")
        if isinstance(topology, dict):
            topologies.append(
                TopologyRecord(
                    source, key, _int(topology.get("node_count")) or 0, _int(topology.get("edge_count")) or 0,
                    _int(topology.get("tls_edge_count")), _int(topology.get("mtls_edge_count")),
                )
            )  # fmt: skip
        runtime = payload.get("runtime")
        if isinstance(runtime, dict) and payload.get("chunk_index") == 0:
            runtimes.append(
                RuntimeRecord(
                    source, key, _text(runtime.get("java_version")), _text(runtime.get("spring_boot_version"))
                )
            )

    @staticmethod
    def _coded_finding(source: str, key: str, payload: Mapping[str, Any]) -> FindingRecord:
        return FindingRecord(
            source=source,
            project_key=key,
            algorithm_family=str(payload.get("algorithm_family")),
            usage_context=str(payload.get("usage_context")),
            location_kind=str(payload.get("location_kind")),
            priority=str(payload.get("priority")),
            key_size_bits=_int(payload.get("key_size_bits")),
            confidence=_float(payload.get("confidence")),
        )
