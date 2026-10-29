"""The corpus tooling against the real database and the real ingest use cases (P6.2): benchmark labels, corpus and benchmark
events in raw, erasure of a corpus project, and the whole path list -> clone -> analyse -> ingest -> report with two small
sample repositories (a fake git copies them; the analyzer answers over fake HTTP)."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from quancrypt_data.domain.corpus import CloneStatus, RepoRef, SelectionPolicy
from quancrypt_data.domain.corpus_events import (
    BENCHMARK_ANALYSIS,
    CORPUS_ANALYSIS,
    AnalysisStats,
    CorpusFinding,
    Runtime,
    UnitAnalysis,
    benchmark_identifier,
    build_events,
    project_key,
    repo_identifier,
)
from quancrypt_data.infrastructure.corpus.corpus_files import LocalCorpusFiles
from quancrypt_data.infrastructure.corpus.csv_stores import CsvCorpusListStore, CsvManifestStore, MarkdownReportWriter
from quancrypt_data.infrastructure.corpus.hasher import HmacProjectKeyHasher
from quancrypt_data.infrastructure.corpus.http_clients import HttpCodeAnalyzer, new_client
from quancrypt_data.infrastructure.corpus.msr_dataset_reader import CsvMsrDatasetReader
from quancrypt_data.infrastructure.persistence.benchmark_labels import PostgresBenchmarkLabelStore
from quancrypt_data.infrastructure.system import SystemClock
from quancrypt_data.port.inbound.corpus import AnalyzeCorpusCommand, BuildCorpusListCommand, CloneCorpusCommand
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand
from quancrypt_data.port.outbound.corpus import BenchmarkLabel, CloneResult, DeliveryResult
from quancrypt_data.usecase.analyze_corpus_service import AnalyzeCorpusService
from quancrypt_data.usecase.build_corpus_list_service import BuildCorpusListService
from quancrypt_data.usecase.clone_corpus_service import CloneCorpusService
from quancrypt_data.usecase.project_analysis import ProjectAnalyzer
from quancrypt_data.usecase.report_corpus_service import ReportCorpusService
from tests.conftest import Stack

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=UTC)
SALT = "s" * 40
MIT = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy. The above copyright notice and this "
    'permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS '
    'IS", WITHOUT WARRANTY OF ANY KIND.'
)


def rows(engine: Engine, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    with engine.begin() as connection:
        return [tuple(r) for r in connection.execute(text(sql), params)]


def finding(index: int = 0) -> CorpusFinding:
    return CorpusFinding(
        file=f"src/main/java/app/C{index}.java",
        line_start=4,
        line_end=4,
        raw_name="SHA1withRSA",
        algorithm_family="RSA",
        usage_context="SIGNATURE",
        location_kind="CODE",
        priority="P0",
        key_size_bits=2048,
        mode=None,
        padding=None,
        hash="SHA-1",
        library="JCA",
        confidence=0.9,
    )


def unit(count: int = 2) -> UnitAnalysis:
    return UnitAnalysis(
        ".", Runtime("21", "3.3.1"), tuple(finding(i) for i in range(count)), AnalysisStats(9, count, 5), None
    )


class TestBenchmarkLabels:
    @pytest.fixture
    def store(self, stack: Stack) -> PostgresBenchmarkLabelStore:
        with stack.instance.migrator_engine().begin() as connection:
            connection.execute(text("TRUNCATE raw.benchmark_label, raw.benchmark_load"))
        return PostgresBenchmarkLabelStore(stack.container.database, SystemClock())

    def labels(self, n: int, prefix: str = "case") -> list[BenchmarkLabel]:
        return [BenchmarkLabel(f"{prefix}-{i}", f"src/{prefix}{i}.java", "weakhash", 328, i % 2 == 0) for i in range(n)]

    def count(self, stack: Stack, benchmark: str) -> int:
        return int(
            rows(
                stack.instance.migrator_engine(),
                "SELECT count(*) FROM raw.benchmark_label WHERE benchmark = :b",
                b=benchmark,
            )[0][0]
        )

    def test_labels_are_written_and_a_reload_replaces_them(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        assert store.replace("owasp-benchmark", self.labels(5)) == 5
        assert store.replace("owasp-benchmark", self.labels(3, "again")) == 3

        assert self.count(stack, "owasp-benchmark") == 3
        ids = {r[0] for r in rows(stack.instance.migrator_engine(), "SELECT case_id FROM raw.benchmark_label")}
        assert ids == {"again-0", "again-1", "again-2"}

    def test_a_benchmark_is_reloaded_without_touching_another(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        store.replace("owasp-benchmark", self.labels(4))
        store.replace("cryptoapi-bench", self.labels(2))

        store.replace("owasp-benchmark", [])

        assert (self.count(stack, "owasp-benchmark"), self.count(stack, "cryptoapi-bench")) == (0, 2)

    def test_a_failed_load_keeps_the_old_labels(self, stack: Stack, store: PostgresBenchmarkLabelStore) -> None:
        store.replace("owasp-benchmark", self.labels(4))
        duplicated = [*self.labels(2), BenchmarkLabel("case-0", None, None, None, True)]

        with pytest.raises(DBAPIError):
            store.replace("owasp-benchmark", duplicated)

        assert self.count(stack, "owasp-benchmark") == 4

    def test_a_benchmark_the_database_does_not_know_is_refused_and_nothing_is_deleted(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        store.replace("owasp-benchmark", self.labels(2))

        with pytest.raises(DBAPIError):
            store.replace("made-up-benchmark", self.labels(1))

        assert self.count(stack, "owasp-benchmark") == 2

    def test_what_the_label_file_does_not_say_is_null_not_a_guess(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        store.replace("cryptoapi-bench", [BenchmarkLabel("x", None, None, None, False)])

        assert rows(
            stack.instance.migrator_engine(),
            "SELECT file_path, category, cwe, expected_vulnerable FROM raw.benchmark_label",
        ) == [(None, None, None, False)]

    def test_the_table_has_no_project_key_so_an_erasure_never_needs_it(self, stack: Stack) -> None:
        columns = {
            c
            for (c,) in rows(
                stack.instance.migrator_engine(),
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'benchmark_label'",
            )
        }

        assert "project_key" not in columns
        assert {"benchmark", "case_id", "expected_vulnerable"} <= columns
        assert "loaded_at" not in columns, "the load time is a fact about the load, kept in raw.benchmark_load (2NF)"

    def test_the_application_role_loads_labels_but_cannot_change_them_in_place_or_read_the_code_list_wrongly(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        store.replace("owasp-benchmark", self.labels(1))
        app = stack.instance.app_engine()

        for sql in (
            "UPDATE raw.benchmark_label SET category = 'x'",
            "TRUNCATE raw.benchmark_label",
            "INSERT INTO ingest.benchmark (code, description, sort_order) VALUES ('new-one', 'x', 3)",
            "DELETE FROM ingest.benchmark",
        ):
            with pytest.raises(DBAPIError, match="permission denied"):
                rows(app, sql)
        assert rows(app, "SELECT count(*) FROM ingest.benchmark") == [(2,)]

    def test_the_load_is_recorded_once_per_benchmark_with_its_time_and_count(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        store.replace("owasp-benchmark", self.labels(5))
        store.replace("owasp-benchmark", self.labels(3, "again"))

        loads = rows(stack.instance.migrator_engine(), "SELECT benchmark, label_count FROM raw.benchmark_load")

        assert loads == [("owasp-benchmark", 3)]

    def test_two_loads_of_one_benchmark_at_once_leave_one_complete_label_set(
        self, stack: Stack, store: PostgresBenchmarkLabelStore
    ) -> None:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        barrier = threading.Barrier(2)

        def load(prefix: str) -> int:
            barrier.wait(timeout=10)
            return store.replace("owasp-benchmark", self.labels(20, prefix))

        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = [f.result(timeout=30) for f in [pool.submit(load, "a"), pool.submit(load, "b")]]

        ids = {r[0] for r in rows(stack.instance.migrator_engine(), "SELECT case_id FROM raw.benchmark_label")}
        assert counts == [20, 20]
        assert ids in ({f"a-{i}" for i in range(20)}, {f"b-{i}" for i in range(20)}), "the union of both loads was kept"
        assert stack.container.database.retries == 0

    @pytest.mark.parametrize(
        ("sql", "constraint"),
        [
            (
                "INSERT INTO raw.benchmark_label (benchmark, case_id, expected_vulnerable, cwe) VALUES ('owasp-benchmark', 'x', true, 0)",
                "ck_benchmark_label_cwe",
            ),
            (
                "INSERT INTO raw.benchmark_label (benchmark, case_id, expected_vulnerable) VALUES ('owasp-benchmark', '  ', true)",
                "ck_benchmark_label_case_id",
            ),
            (
                "INSERT INTO raw.benchmark_load (benchmark, loaded_at, label_count) VALUES ('owasp-benchmark', now(), -1)",
                "ck_benchmark_load_label_count",
            ),
            (
                "INSERT INTO ingest.benchmark (code, description, sort_order) VALUES ('Bad Code', 'x', 9)",
                "ck_benchmark_code",
            ),
        ],
    )
    def test_every_check_of_the_new_tables_refuses_its_violation(self, stack: Stack, sql: str, constraint: str) -> None:
        with pytest.raises(DBAPIError, match=constraint):
            rows(stack.instance.migrator_engine(), sql)

    def test_the_read_role_of_the_warehouse_sees_none_of_the_landing_tables(self, stack: Stack) -> None:
        reader = stack.instance.reader_engine()

        for table in ("raw.benchmark_label", "raw.benchmark_load", "ingest.benchmark"):
            with pytest.raises(DBAPIError, match="permission denied"):
                rows(reader, f"SELECT 1 FROM {table}")


class TestCorpusEventsInRaw:
    def ingest(self, stack: Stack, events: Sequence[Mapping[str, object]]) -> Any:
        return stack.container.ingest_events.execute(IngestEventsCommand(items=list(events)))

    def test_corpus_and_benchmark_events_are_stored_with_their_own_sources(self, stack: Stack) -> None:
        corpus = build_events(CORPUS_ANALYSIS, "a" * 64, [unit()], NOW)
        bench = build_events(BENCHMARK_ANALYSIS, "b" * 64, [unit(1)], NOW, benchmark="owasp-benchmark")

        result = self.ingest(stack, [*corpus, *bench])

        assert (result.accepted, result.quarantined) == (2, 0)
        assert rows(
            stack.instance.migrator_engine(), "SELECT event_type, source FROM raw.event ORDER BY event_type"
        ) == [
            ("benchmark_analysis", "benchmark"),
            ("corpus_analysis", "corpus"),
        ]

    def test_the_same_analysis_sent_again_is_a_duplicate(self, stack: Stack) -> None:
        events = build_events(CORPUS_ANALYSIS, "a" * 64, [unit()], NOW)
        self.ingest(stack, events)

        again = self.ingest(stack, build_events(CORPUS_ANALYSIS, "a" * 64, [unit()], datetime(2027, 1, 1, tzinfo=UTC)))

        assert (again.accepted, again.duplicate) == (0, 1)
        assert rows(stack.instance.migrator_engine(), "SELECT count(*) FROM raw.event") == [(1,)]

    def test_an_event_that_breaks_the_schema_is_quarantined_not_stored(self, stack: Stack) -> None:
        event = build_events(CORPUS_ANALYSIS, "a" * 64, [unit()], NOW)[0]
        event["payload"]["findings"][0]["priority"] = "P9"  # type: ignore[index]

        result = self.ingest(stack, [event])

        assert (result.accepted, result.quarantined) == (0, 1)

    def test_the_revocation_of_a_corpus_project_key_erases_its_events_and_no_other(self, stack: Stack) -> None:
        mine = build_events(CORPUS_ANALYSIS, "a" * 64, [unit()], NOW)
        other = build_events(CORPUS_ANALYSIS, "c" * 64, [unit()], NOW)
        self.ingest(stack, [*mine, *other])
        revoke = {
            "event_id": "00000000-0000-4000-8000-0000000000aa",
            "event_type": "consent_revoked",
            "schema_version": 1,
            "occurred_at": "2026-10-28T10:00:00Z",
            "project_key": "a" * 64,
            "payload": {"consent_type": "WAREHOUSE_ANALYTICS", "delete_requested": False},
        }

        result = self.ingest(stack, [revoke])

        assert result.consent_revoked == 1
        assert rows(stack.instance.migrator_engine(), "SELECT project_key FROM raw.event") == [("c" * 64,)]


def make_repository(root: Path, name: str, *, license_text: str, spring: bool = True) -> None:
    project = root / name
    for service in ("orders", "payments", "users"):
        (project / service / "src" / "main" / "java").mkdir(parents=True)
        (project / service / "pom.xml").write_text("<project><artifactId>x</artifactId></project>", encoding="utf-8")
        (project / service / "src" / "main" / "java" / "A.java").write_text("class A {}", encoding="utf-8")
    (project / "pom.xml").write_text(
        "<project><parent>spring-boot-starter-parent</parent></project>" if spring else "<project/>", encoding="utf-8"
    )
    (project / "LICENSE").write_text(license_text, encoding="utf-8")


class CopyingGit:
    """A git that 'clones' by copying a prepared sample repository: no network."""

    def __init__(self, samples: Path, corpus: Path) -> None:
        self._samples, self._corpus = samples, corpus

    def clone(self, repo: RepoRef) -> CloneResult:
        shutil.copytree(self._samples / repo.dir_name, self._corpus / repo.dir_name)
        return CloneResult(commit_sha="a" * 40, default_branch="main")


class InProcessSink:
    """Delivers to the real ingest use case of the stack instead of over HTTP."""

    def __init__(self, stack: Stack) -> None:
        self._stack = stack

    def send(self, events: Sequence[Mapping[str, object]]) -> DeliveryResult:
        result = self._stack.container.ingest_events.execute(IngestEventsCommand(items=list(events)))
        return DeliveryResult(
            result.accepted, result.duplicate, result.quarantined, result.superseded, result.consent_revoked
        )


ANALYZER = "http://127.0.0.1:8082"


def analyzer_answer(file_count: int) -> dict[str, object]:
    return {
        "analysis_id": "00000000-0000-4000-8000-000000000001",
        "project_type": "MAVEN",
        "runtime": {"java_version": "21", "spring_boot_version": "3.3.1"},
        "findings": [
            {
                "file": f"orders/src/main/java/app/C{i}.java",
                "line_start": 3,
                "line_end": 3,
                "raw_name": "SHA1withRSA",
                "symbol": "C#sign",
                "algorithm_family": "RSA",
                "mode": None,
                "padding": None,
                "hash": "SHA-1",
                "key_size_bits": 2048,
                "usage_context": "SIGNATURE",
                "location_kind": "CODE",
                "priority": "P0",
                "library": "JCA",
                "confidence": 0.9,
                "detector_id": "java.jca",
            }
            for i in range(file_count)
        ],
        "cbom": {"bomFormat": "CycloneDX", "specVersion": "1.6"},
        "stats": {"files_scanned": 9, "findings_total": file_count, "duration_ms": 12},
    }


class TestTheWholePath:
    @respx.mock
    def test_two_sample_repositories_go_from_the_dataset_to_raw_and_the_report(
        self, stack: Stack, tmp_path: Path
    ) -> None:
        samples, corpus = tmp_path / "samples", tmp_path / "corpus"
        samples.mkdir()
        corpus.mkdir()
        make_repository(samples, "acme__shop", license_text=MIT)
        make_repository(samples, "acme__locked", license_text="All rights reserved.")
        dataset = tmp_path / "msr.csv"
        dataset.write_text("repo_url\nhttps://github.com/acme/shop\nhttps://github.com/acme/locked\n", encoding="utf-8")
        listing = CsvCorpusListStore(tmp_path / "reference" / "corpus_projects.csv")
        manifest = CsvManifestStore(tmp_path / "reports" / "corpus_manifest.csv")
        files = LocalCorpusFiles(corpus)
        clock = SystemClock()
        analyzer = HttpCodeAnalyzer(ANALYZER, new_client(5, "t" * 40), sleep=lambda _: None)
        respx.post(f"{ANALYZER}/api/v1/analyses").mock(return_value=httpx.Response(200, json=analyzer_answer(3)))
        respx.post(f"{ANALYZER}/api/v1/topologies").mock(
            return_value=httpx.Response(
                200, json={"nodes": [{}, {}, {}], "edges": [{"protocol": "HTTP", "tls": True, "mtls": False}]}
            )
        )
        sink = InProcessSink(stack)
        analyze = AnalyzeCorpusService(
            listing, manifest, ProjectAnalyzer(analyzer, files, "/corpus"), sink, HmacProjectKeyHasher(SALT), clock
        )

        built = BuildCorpusListService(CsvMsrDatasetReader(), listing, SelectionPolicy()).execute(
            BuildCorpusListCommand(dataset, 100)
        )
        cloned = CloneCorpusService(listing, manifest, CopyingGit(samples, corpus), files).execute(
            CloneCorpusCommand(0, 10, 10 * 1024**3)
        )
        analysed = analyze.execute(AnalyzeCorpusCommand(0, 10))
        again = analyze.execute(AnalyzeCorpusCommand(0, 10))
        report = ReportCorpusService(
            listing, manifest, MarkdownReportWriter(tmp_path / "reports" / "corpus_run.md"), clock
        ).execute()

        assert (built.candidates, built.selected) == (2, 2)
        assert (cloned.attempted, cloned.cloned, cloned.excluded) == (2, 1, {"license-unverified": 1})
        assert not files.exists("acme__locked"), "a project whose license cannot be verified is removed from disk"
        assert (analysed.analyzed, analysed.findings_total, analysed.accepted, analysed.quarantined) == (1, 3, 1, 0)
        assert again.attempted == 0, "an analysed project is not analysed again"

        engine = stack.instance.migrator_engine()
        stored = rows(engine, "SELECT event_type, source, project_key, payload FROM raw.event")
        assert len(stored) == 1
        event_type, source, key, payload = stored[0]
        assert (event_type, source) == ("corpus_analysis", "corpus")
        assert key == project_key(SALT, repo_identifier(RepoRef.parse("https://github.com/acme/shop")))
        assert len(payload["findings"]) == 3 and payload["topology"]["edge_count"] == 1
        everything = str(rows(engine, "SELECT payload::text FROM raw.event")) + str(
            rows(engine, "SELECT record::text FROM quarantine.event")
        )
        for identifying in ("acme", "shop", "github", "/corpus", str(tmp_path)):
            assert identifying not in everything, identifying

        entry = manifest.load()[RepoRef.parse("https://github.com/acme/shop").canonical]
        assert (entry.status, entry.license_verified, entry.commit_sha) == (CloneStatus.CLONED, "MIT", "a" * 40)
        assert (entry.findings_total, entry.units) == (3, 1)
        text_ = (tmp_path / "reports" / "corpus_run.md").read_text(encoding="utf-8")
        assert "| Elenen (toplam) | 1 |" in text_ and "https://github.com/acme/locked" in text_
        assert (report.listed, report.analyzed) == (2, 1)

    def test_a_second_delivery_of_the_same_run_is_a_duplicate_not_a_second_row(self, stack: Stack) -> None:
        key = project_key(SALT, "https://github.com/acme/shop")
        sink = InProcessSink(stack)
        events = build_events(CORPUS_ANALYSIS, key, [unit(3)], NOW)

        first = sink.send(events)
        second = sink.send(events)

        assert (first.accepted, second.accepted, second.duplicate) == (1, 0, 1)
        assert rows(stack.instance.migrator_engine(), "SELECT count(*) FROM raw.event") == [(1,)]

    def test_benchmark_identifier_keys_do_not_collide_with_repository_keys(self) -> None:
        assert project_key(SALT, benchmark_identifier("owasp-benchmark")) != project_key(
            SALT, "https://github.com/acme/shop"
        )
