"""The prep layer against the real database (P6.4, acid-3nf-database section 7): the migration and the role's rights,
the pipeline end to end, idempotency, atomicity, constraints, the leak test (H6) and the erasure of a project key."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from quancrypt_data.domain.corpus_events import (
    CORPUS_ANALYSIS,
    AnalysisStats,
    CorpusFinding,
    Runtime,
    UnitAnalysis,
    build_events,
)
from quancrypt_data.domain.filters.deduplicator import Deduplicator
from quancrypt_data.domain.filters.generated_code_excluder import GeneratedCodeExcluder
from quancrypt_data.domain.filters.missing_value_handler import MissingValueHandler
from quancrypt_data.domain.filters.outlier_flagger import OutlierFlagger
from quancrypt_data.domain.filters.test_code_flagger import TestCodeFlagger
from quancrypt_data.domain.filters.type_caster import TypeCaster
from quancrypt_data.domain.prep import (
    ALGORITHM_FAMILIES,
    LOCATION_KINDS,
    PRIORITIES,
    PROJECT_ORIGINS,
    USAGE_CONTEXTS,
    RecordFilter,
    Rejection,
)
from quancrypt_data.infrastructure.filters.anonymizer import Anonymizer
from quancrypt_data.infrastructure.filters.canonicalizer import Canonicalizer
from quancrypt_data.infrastructure.filters.schema_validator import SchemaValidator
from quancrypt_data.infrastructure.persistence.benchmark_labels import PostgresBenchmarkLabelStore
from quancrypt_data.infrastructure.persistence.prep_store import (
    PostgresPrepReader,
    PostgresPrepRepository,
    PostgresRawEventSource,
)
from quancrypt_data.infrastructure.prep.report_files import FilePrepReportWriter
from quancrypt_data.infrastructure.profiling.dictionary_csv import CsvCanonicalDictionary
from quancrypt_data.infrastructure.redaction.redactor import Redactor
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog
from quancrypt_data.infrastructure.system import SystemClock
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand
from quancrypt_data.port.outbound.corpus import BenchmarkLabel
from quancrypt_data.usecase.preprocess_service import PreprocessService
from tests.conftest import Stack
from tests.support.envelopes import KEY_A, envelope
from tests.support.prep_fakes import KEY as PREP_FAKE_KEY
from tests.support.prep_fakes import check_repository_replaces_a_project, check_source_on_an_empty_raw, content

pytestmark = pytest.mark.postgres

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SALT = "s" * 40
CORPUS_KEY = "c" * 64


def rows(engine: Engine, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        return [tuple(r) for r in connection.execute(text(sql), params)]


def corpus_events(key: str, *findings: CorpusFinding, unit: str = "svc-a") -> list[dict[str, object]]:
    analysis = UnitAnalysis(unit, Runtime("21", "3.3.1"), findings, AnalysisStats(9, len(findings), 5), None)
    return build_events(CORPUS_ANALYSIS, key, [analysis], datetime(2026, 10, 28, tzinfo=UTC))


def corpus_finding(file: str = "src/main/java/com/acme/Shop.java", line: int = 3, **fields: object) -> CorpusFinding:
    base: dict[str, object] = {
        "file": file, "line_start": line, "line_end": line, "raw_name": "SHA1withRSA", "algorithm_family": "RSA",
        "usage_context": "SIGNATURE", "location_kind": "CODE", "priority": "P0", "key_size_bits": 2048, "mode": None,
        "padding": "PKCS1_V1_5", "hash": "SHA-1", "library": "JCA", "confidence": 0.9,
    }  # fmt: skip
    base.update(fields)
    return CorpusFinding(**base)  # type: ignore[arg-type]


def raw_id(stack: Stack, key: str = CORPUS_KEY) -> str:
    """The id of an event of the key that is in raw (the rows of prep keep the event they came from)."""
    return str(
        rows(stack.instance.migrator_engine(), "SELECT event_id FROM raw.event WHERE project_key = :k", k=key)[0][0]
    )


def pipeline(stack: Stack, reports: Path) -> PreprocessService:
    database = stack.container.database
    redactor = Redactor.from_file(CONTRACTS / "redaction-rules.yaml")
    filters: list[RecordFilter] = [
        SchemaValidator(JsonSchemaCatalog(CONTRACTS / "schemas" / "events")), Deduplicator(), GeneratedCodeExcluder(),
        TestCodeFlagger(), Canonicalizer(CsvCanonicalDictionary(CONTRACTS / "canonical_dictionary.csv")),
        Anonymizer(SALT, redactor), MissingValueHandler(), OutlierFlagger(), TypeCaster(),
    ]  # fmt: skip
    return PreprocessService(
        PostgresRawEventSource(database), filters, PostgresPrepRepository(database, SystemClock()),
        PostgresPrepReader(database), redactor, FilePrepReportWriter(reports), SystemClock(),
    )  # fmt: skip


def ingest(stack: Stack, *items: dict[str, object]) -> None:
    stack.container.ingest_events.execute(IngestEventsCommand(items=list(items)))


PREP_TABLES = ("prep.project_snapshot", "prep.analysis_unit", "prep.finding", "prep.topology_summary",
               "prep.service_link", "prep.scope_decision", "prep.benchmark_label")  # fmt: skip


def snapshot_of_prep(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    state = {table: sorted(rows(engine, f"SELECT * FROM {table}"), key=repr) for table in PREP_TABLES}  # noqa: S608
    state["quarantine.prep_record"] = sorted(
        rows(engine, "SELECT id, project_key, raw_event_id, filter_code, error_code, error_message, rows_set_aside "
                     "FROM quarantine.prep_record"), key=repr,
    )  # fmt: skip
    return state


class TestSchema:
    def test_the_lookups_equal_the_domain_code_lists(self, stack: Stack) -> None:
        engine = stack.instance.migrator_engine()
        for table, codes in (("prep.algorithm_family", ALGORITHM_FAMILIES), ("prep.usage_context", USAGE_CONTEXTS),
                             ("prep.location_kind", LOCATION_KINDS), ("prep.priority", PRIORITIES),
                             ("prep.project_origin", PROJECT_ORIGINS)):  # fmt: skip
            assert {code for (code,) in rows(engine, f"SELECT code FROM {table}")} == codes, table  # noqa: S608

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE prep.finding SET priority = 'P0'",
            "UPDATE prep.project_snapshot SET is_outlier_project = true",
            "INSERT INTO prep.priority (code, description, sort_order) VALUES ('P9', 'x', 9)",
            "CREATE TABLE prep.extra (id integer)",
        ],
    )
    def test_the_application_role_writes_rows_and_nothing_else(self, stack: Stack, statement: str) -> None:
        with pytest.raises(DBAPIError, match="permission denied"):
            stack.container.database.run(lambda: stack.container.database.connection().execute(text(statement)))

    def test_key_size_known_is_derived_from_the_key_size(self, stack: Stack) -> None:
        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding()))  # the project is in raw
        repository = PostgresPrepRepository(stack.container.database, SystemClock())
        repository.replace_project(CORPUS_KEY, content(CORPUS_KEY, findings=2, source_event_id=raw_id(stack)), [])
        engine = stack.instance.migrator_engine()

        assert rows(engine, "SELECT DISTINCT key_size_known FROM prep.finding") == [(True,)]


class TestConstraints:
    @pytest.mark.parametrize(
        ("statement", "constraint"),
        [
            ("INSERT INTO prep.service_link VALUES ('{k}', '.', 0, 'HTTP', false, true)", "ck_service_link_mtls"),
            ("UPDATE prep.finding SET line_end = 1, line_start = 5", "ck_finding_line_end"),
            ("UPDATE prep.finding SET priority = 'P9'", "fk_finding_priority"),
            ("UPDATE prep.finding SET confidence = 2", "ck_finding_confidence"),
        ],
    )
    def test_each_rule_is_refused_by_the_database(self, stack: Stack, statement: str, constraint: str) -> None:
        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding()))  # the project is in raw
        PostgresPrepRepository(stack.container.database, SystemClock()).replace_project(
            CORPUS_KEY, content(CORPUS_KEY, source_event_id=raw_id(stack)), []
        )
        with pytest.raises(IntegrityError, match=constraint), stack.instance.migrator_engine().begin() as connection:
            connection.execute(text(statement.format(k=CORPUS_KEY)))


class TestPipeline:
    def test_raw_becomes_clean_anonymous_prep_and_the_funnel_adds_up(self, stack: Stack, tmp_path: Path) -> None:
        ingest(
            stack,
            *corpus_events(
                CORPUS_KEY,
                corpus_finding(),
                corpus_finding(),  # a repeat
                corpus_finding("target/generated-sources/Gen.java"),  # generated code
                corpus_finding("src/test/java/com/acme/ShopTest.java", line=9),  # test code, kept
                corpus_finding(line=12, key_size_bits=None, mode="GCM-SIV"),  # unknown size, unmapped mode
            ),
            envelope("finding_detected"), envelope("topology_recorded"), envelope("scope_decision"),
        )  # fmt: skip
        PostgresBenchmarkLabelStore(stack.container.database, SystemClock()).replace(
            "owasp-benchmark", [BenchmarkLabel("c1", "src/main/java/BenchmarkTest00001.java", "crypto", 327, True)]
        )

        result = pipeline(stack, tmp_path).execute()

        engine = stack.instance.migrator_engine()
        assert (result.findings, result.leaks) == (4, {})
        assert rows(engine, "SELECT count(*) FROM prep.finding WHERE in_test_code") == [(1,)]
        assert rows(engine, "SELECT mode, key_size_known FROM prep.finding WHERE key_size_bits IS NULL") == [
            ("UNKNOWN", False)
        ]
        paths = [p for (p,) in rows(engine, "SELECT file_path FROM prep.finding WHERE file_path IS NOT NULL")]
        assert paths and all("acme" not in p and "Shop" not in p and p.startswith("src/") for p in paths)
        assert {u for (u,) in rows(engine, "SELECT unit_path FROM prep.analysis_unit")} >= {"."}
        assert "svc-a" not in {u for (u,) in rows(engine, "SELECT unit_path FROM prep.analysis_unit")}
        assert rows(engine, "SELECT protocol, tls, mtls FROM prep.service_link") == [("HTTP", True, False)]
        assert rows(engine, "SELECT count(*) FROM prep.scope_decision") == [(1,)]
        assert rows(engine, "SELECT count(*) FROM prep.benchmark_label WHERE file_path LIKE 'src/main/java/%'") == [
            (1,)
        ]
        report = (tmp_path / "preprocessing_report.md").read_text(encoding="utf-8")
        assert "Huni tutarlı (her filtrenin çıkanı bir sonrakinin gireni): evet" in report

    def test_running_twice_gives_the_same_prep(self, stack: Stack, tmp_path: Path) -> None:
        ingest(
            stack, *corpus_events(CORPUS_KEY, corpus_finding(), corpus_finding(line=7)), envelope("finding_detected")
        )
        run = pipeline(stack, tmp_path)
        engine = stack.instance.migrator_engine()

        run.execute()
        first = snapshot_of_prep(engine)
        run.execute()

        assert snapshot_of_prep(engine) == first and first["prep.finding"]

    def test_a_raw_identifier_or_a_secret_never_reaches_prep(self, stack: Stack, tmp_path: Path) -> None:
        ingest(
            stack,
            *corpus_events(
                CORPUS_KEY,
                corpus_finding(),
                corpus_finding("/home/olcay/work/Secret.java", line=4),
                corpus_finding(line=5, library="AKIAIOSFODNN7EXAMPLE"),
            ),
        )

        result = pipeline(stack, tmp_path).execute()

        texts = PostgresPrepReader(stack.container.database).text_values()
        assert result.leaks == {} and not any("olcay" in t or "AKIA" in t for t in texts)

    def test_a_long_anonymised_path_is_not_read_as_one_random_string(self, stack: Stack, tmp_path: Path) -> None:
        deep = "billing-service/payment-core/card-adapter/src/main/resources/gateway-config/application.properties"
        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding(deep)))

        result = pipeline(stack, tmp_path).execute()

        paths = PostgresPrepReader(stack.container.database).path_values()
        assert any(len(p) > 32 and p.count("/") >= 6 for p in paths), paths
        assert result.leaks == {}

    def test_a_failed_write_leaves_the_project_as_it_was(self, stack: Stack) -> None:
        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding()))  # the project is in raw
        repository = PostgresPrepRepository(stack.container.database, SystemClock())
        repository.replace_project(CORPUS_KEY, content(CORPUS_KEY, findings=2, source_event_id=raw_id(stack)), [])
        broken = content(CORPUS_KEY, findings=3, source_event_id=raw_id(stack))
        broken = type(broken)(broken.project, broken.units, (*broken.findings[:2], *(
            type(f)(**{**vars(f), "priority": "P9"}) for f in broken.findings[2:])), (), (), ())  # fmt: skip

        with pytest.raises(IntegrityError):
            repository.replace_project(CORPUS_KEY, broken, [])

        assert rows(stack.instance.migrator_engine(), "SELECT count(*) FROM prep.finding") == [(2,)]


class TestRevocationRace:
    def test_a_project_raw_no_longer_has_is_not_written_back_from_an_earlier_read(self, stack: Stack) -> None:
        repository = PostgresPrepRepository(stack.container.database, SystemClock())
        # The pipeline read the project, then a consent revocation erased it from raw: nothing may be written.
        repository.replace_project(CORPUS_KEY, content(CORPUS_KEY, findings=2), [])

        engine = stack.instance.migrator_engine()
        assert rows(engine, "SELECT count(*) FROM prep.project_snapshot") == [(0,)]
        assert rows(engine, "SELECT count(*) FROM prep.finding") == [(0,)]

    def test_rows_of_events_a_revocation_deleted_are_not_written_back_when_the_key_comes_back(
        self, stack: Stack
    ) -> None:
        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding()))
        old = raw_id(stack)
        engine = stack.instance.migrator_engine()
        with engine.begin() as connection:  # the revocation deleted the old event; the key then returned with a new one
            connection.execute(text("DELETE FROM raw.event WHERE project_key = :k"), {"k": CORPUS_KEY})
        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding("src/main/java/Other.java", line=9), unit="svc-b"))
        repository = PostgresPrepRepository(stack.container.database, SystemClock())

        repository.replace_project(CORPUS_KEY, content(CORPUS_KEY, findings=2, source_event_id=old), [])

        assert rows(engine, "SELECT count(*) FROM prep.finding") == [(0,)], "the old event's rows were not written"

    def test_the_write_waits_for_the_lock_the_erasure_takes(self, stack: Stack) -> None:
        import threading

        ingest(stack, *corpus_events(CORPUS_KEY, corpus_finding()))
        repository = PostgresPrepRepository(stack.container.database, SystemClock())
        engine = stack.instance.migrator_engine()
        done = threading.Event()

        with engine.begin() as holder:  # the erasure's lock, held in another transaction
            holder.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"),
                {"name": f"quancrypt-ingest:{CORPUS_KEY}"},
            )

            def write() -> None:
                repository.replace_project(
                    CORPUS_KEY, content(CORPUS_KEY, findings=1, source_event_id=raw_id(stack)), []
                )
                done.set()

            worker = threading.Thread(target=write)
            worker.start()
            assert not done.wait(1.0), "the write did not wait for the lock"
            holder.execute(text("DELETE FROM raw.event WHERE project_key = :k"), {"k": CORPUS_KEY})  # the erasure
        worker.join(10)

        assert done.is_set()
        assert rows(engine, "SELECT count(*) FROM prep.finding") == [(0,)], "what the erasure removed stays removed"


class TestErasure:
    def test_consent_revoked_also_erases_the_quarantine_records_of_the_key(self, stack: Stack) -> None:
        ingest(stack, envelope("finding_detected"))
        repository = PostgresPrepRepository(stack.container.database, SystemClock())
        rejection = Rejection("Anonymizer", "secret-match", "finding", KEY_A, raw_id(stack, KEY_A))
        repository.replace_project(KEY_A, None, [rejection])
        engine = stack.instance.migrator_engine()
        assert rows(engine, "SELECT count(*) FROM quarantine.prep_record WHERE project_key = :k", k=KEY_A) == [(1,)]

        ingest(stack, envelope("consent_revoked", occurred_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                               event_id=str(uuid.uuid4())))  # fmt: skip

        assert rows(engine, "SELECT count(*) FROM quarantine.prep_record WHERE project_key = :k", k=KEY_A) == [(0,)]
        audited = dict(rows(engine, "SELECT table_name, deleted_rows FROM ingest.ingest_audit_table"))
        assert audited["quarantine.prep_record"] == 1

    def test_consent_revoked_erases_the_prep_rows_of_the_key_and_keeps_the_audit(
        self, stack: Stack, tmp_path: Path
    ) -> None:
        ingest(stack, envelope("finding_detected"), envelope("scope_decision"), envelope("topology_recorded"),
               *corpus_events(CORPUS_KEY, corpus_finding()))  # fmt: skip
        pipeline(stack, tmp_path).execute()
        engine = stack.instance.migrator_engine()
        assert rows(engine, "SELECT count(*) FROM prep.project_snapshot") == [(2,)]

        ingest(stack, envelope("consent_revoked", occurred_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                               event_id=str(uuid.uuid4())))  # fmt: skip

        for table in PREP_TABLES[:-1]:
            assert rows(engine, f"SELECT count(*) FROM {table} WHERE project_key = :k", k=KEY_A) == [(0,)], table  # noqa: S608
        assert rows(engine, "SELECT count(*) FROM prep.project_snapshot") == [(1,)], "the other project stays"
        audited = dict(rows(engine, "SELECT table_name, deleted_rows FROM ingest.ingest_audit_table"))
        assert audited["prep.finding"] == 1 and audited["prep.project_snapshot"] == 1


class TestPorts:
    def test_the_postgres_source_passes_the_source_cases(self, stack: Stack) -> None:
        check_source_on_an_empty_raw(PostgresRawEventSource(stack.container.database))

    def test_the_postgres_store_passes_the_repository_cases(self, stack: Stack) -> None:
        ingest(stack, *corpus_events(PREP_FAKE_KEY, corpus_finding()))  # the project is in raw
        database = stack.container.database
        check_repository_replaces_a_project(
            PostgresPrepRepository(database, SystemClock()),
            PostgresPrepReader(database),
            raw_id(stack, PREP_FAKE_KEY),
        )

    def test_the_source_reads_in_a_read_only_transaction(self, stack: Stack) -> None:
        source = PostgresRawEventSource(stack.container.database)

        with pytest.raises(DBAPIError, match="read-only transaction"):
            source._read_only(lambda: stack.container.database.connection().execute(text("DELETE FROM raw.event")))
