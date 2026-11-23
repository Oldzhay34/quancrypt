"""The raw reader against the real database (P6.3): what it extracts, that it never changes raw (checksums), and that its
transactions are READ ONLY (the database refuses a write)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from quancrypt_data.domain.corpus_events import (
    CORPUS_ANALYSIS,
    AnalysisStats,
    CorpusFinding,
    Runtime,
    UnitAnalysis,
    build_events,
)
from quancrypt_data.infrastructure.persistence.benchmark_labels import PostgresBenchmarkLabelStore
from quancrypt_data.infrastructure.persistence.raw_reader import PostgresRawDataReader
from quancrypt_data.infrastructure.system import SystemClock
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand
from quancrypt_data.port.outbound.corpus import BenchmarkLabel
from tests.conftest import Stack
from tests.support.envelopes import KEY_A, envelope
from tests.support.profiling_fakes import check_reader_on_an_empty_raw

pytestmark = pytest.mark.postgres


def corpus_events(key: str, count: int) -> list[dict[str, object]]:
    finding = CorpusFinding(
        file="src/main/java/A.java", line_start=1, line_end=1, raw_name="SHA1withRSA", algorithm_family="RSA",
        usage_context="SIGNATURE", location_kind="CODE", priority="P0", key_size_bits=2048, mode=None, padding=None,
        hash="SHA-1", library="JCA", confidence=0.9,
    )  # fmt: skip
    unit = UnitAnalysis(".", Runtime("21", "3.3.1"), (finding,) * count, AnalysisStats(9, count, 5), None)
    return build_events(CORPUS_ANALYSIS, key, [unit], datetime(2026, 10, 28, tzinfo=UTC))


def test_the_reader_extracts_findings_runtimes_and_sources_and_changes_nothing(stack: Stack) -> None:
    items = [*corpus_events("c" * 64, 3), envelope("finding_detected"), envelope("scope_decision")]
    stack.container.ingest_events.execute(IngestEventsCommand(items=items))
    reader = PostgresRawDataReader(stack.container.database)

    before = reader.checksums()
    snapshot = reader.snapshot()
    after = reader.checksums()

    assert before == after
    assert {c.table for c in before} == {"raw.event", "quarantine.event", "raw.benchmark_label", "raw.benchmark_load"}
    assert next(c for c in before if c.table == "raw.event").rows == 3
    assert {(s.event_type, s.count) for s in snapshot.sources} == {
        ("corpus_analysis", 1),
        ("finding_detected", 1),
        ("scope_decision", 1),
    }
    corpus = [f for f in snapshot.findings if f.source == "corpus"]
    assert len(corpus) == 3 and corpus[0].raw_name == "SHA1withRSA"
    coded = [f for f in snapshot.findings if f.source == "core-service"]
    assert len(coded) == 1 and coded[0].file is None and coded[0].project_key == KEY_A
    assert [r.java_version for r in snapshot.runtimes] == ["21"]
    assert len(snapshot.scopes) == 1
    assert any(t.where == "findings.raw_name" for t in snapshot.texts)


def test_a_path_is_read_below_its_analysis_unit_so_two_services_are_not_one_file(stack: Stack) -> None:
    finding = CorpusFinding(
        file="src/main/resources/client.keystore", line_start=None, line_end=None, raw_name="JKS keystore",
        algorithm_family="UNKNOWN", usage_context="KEYSTORE", location_kind="KEYSTORE_FILE", priority="P3",
        key_size_bits=None, mode=None, padding=None, hash=None, library=None, confidence=0.9,
    )  # fmt: skip
    units = [
        UnitAnalysis(name, Runtime("21", None), (finding,), AnalysisStats(1, 1, 1), None) for name in ("svc-a", "svc-b")
    ]
    events = build_events(CORPUS_ANALYSIS, "d" * 64, units, datetime(2026, 10, 28, tzinfo=UTC))
    stack.container.ingest_events.execute(IngestEventsCommand(items=events))

    snapshot = PostgresRawDataReader(stack.container.database).snapshot()

    assert sorted(f.file or "" for f in snapshot.findings) == [
        "svc-a/src/main/resources/client.keystore",
        "svc-b/src/main/resources/client.keystore",
    ]


def test_a_change_to_raw_changes_the_checksum(stack: Stack) -> None:
    reader = PostgresRawDataReader(stack.container.database)
    before = reader.checksums()

    stack.container.ingest_events.execute(IngestEventsCommand(items=[envelope()]))

    assert reader.checksums() != before


@pytest.mark.parametrize(
    ("table", "update"),
    [
        ("raw.event", "UPDATE raw.event SET project_key = repeat('e', 64)"),
        ("raw.event", "UPDATE raw.event SET occurred_at = occurred_at + interval '1 second'"),
        ("quarantine.event", "UPDATE quarantine.event SET error_message = error_message || '.'"),
        ("raw.benchmark_label", "UPDATE raw.benchmark_label SET category = 'changed'"),
        ("raw.benchmark_load", "UPDATE raw.benchmark_load SET label_count = label_count + 1"),
    ],
)
def test_a_change_to_any_column_of_a_row_changes_the_checksum_of_its_table(
    stack: Stack, table: str, update: str
) -> None:
    stack.container.ingest_events.execute(IngestEventsCommand(items=[envelope(), envelope(payload={"priority": "P9"})]))
    PostgresBenchmarkLabelStore(stack.container.database, SystemClock()).replace(
        "owasp-benchmark", [BenchmarkLabel("case-1", "A.java", "crypto", 327, True)]
    )
    reader = PostgresRawDataReader(stack.container.database)
    before = {c.table: c for c in reader.checksums()}
    assert before[table].rows == 1, "every table holds one row before the change"

    with stack.instance.migrator_engine().begin() as connection:
        connection.execute(text(update))

    after = {c.table: c for c in reader.checksums()}
    assert after[table].rows == before[table].rows
    assert after[table].digest != before[table].digest
    assert all(after[other] == before[other] for other in before if other != table)


def test_the_postgres_reader_passes_the_reader_cases(stack: Stack) -> None:
    check_reader_on_an_empty_raw(PostgresRawDataReader(stack.container.database))


def test_the_transactions_of_the_reader_are_read_only(stack: Stack) -> None:
    reader = PostgresRawDataReader(stack.container.database)

    def write() -> None:
        stack.container.database.connection().execute(text("DELETE FROM raw.event"))

    with pytest.raises(DBAPIError, match="read-only transaction"):
        reader._read_only(write)
