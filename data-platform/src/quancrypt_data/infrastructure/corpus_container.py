"""The composition root of the corpus command line and flows (hexagonal-service section 2): the only module of the
corpus
tooling that sees every layer. It reads the settings, builds the adapters, the use cases and the facade."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from quancrypt_data.domain.corpus import SelectionPolicy
from quancrypt_data.facade.corpus_facade import CorpusFacade
from quancrypt_data.infrastructure.corpus.corpus_files import LocalCorpusFiles
from quancrypt_data.infrastructure.corpus.csv_stores import CsvCorpusListStore, CsvManifestStore, MarkdownReportWriter
from quancrypt_data.infrastructure.corpus.git_repository import SubprocessGitRepository
from quancrypt_data.infrastructure.corpus.hasher import HmacProjectKeyHasher
from quancrypt_data.infrastructure.corpus.http_clients import HttpCodeAnalyzer, HttpEventSink, new_client
from quancrypt_data.infrastructure.corpus.msr_dataset_reader import CsvMsrDatasetReader
from quancrypt_data.infrastructure.corpus.settings import CorpusSettings, load_corpus_settings
from quancrypt_data.infrastructure.logging_setup import configure_logging
from quancrypt_data.infrastructure.persistence.benchmark_labels import PostgresBenchmarkLabelStore
from quancrypt_data.infrastructure.persistence.database import Database
from quancrypt_data.infrastructure.settings import ConfigError
from quancrypt_data.infrastructure.system import SystemClock
from quancrypt_data.port.outbound.corpus import BenchmarkLabel, BenchmarkLabelReader
from quancrypt_data.usecase.analyze_corpus_service import AnalyzeCorpusService
from quancrypt_data.usecase.build_corpus_list_service import BuildCorpusListService
from quancrypt_data.usecase.clone_corpus_service import CloneCorpusService
from quancrypt_data.usecase.load_benchmarks_service import LoadBenchmarksService
from quancrypt_data.usecase.project_analysis import ProjectAnalyzer
from quancrypt_data.usecase.report_corpus_service import ReportCorpusService

LIST_FILE = "corpus_projects.csv"
MANIFEST_FILE = "corpus_manifest.csv"
REPORT_FILE = "corpus_run.md"


class _NoDatabase:
    """The label store of a command that was started without the database settings."""

    def replace(self, benchmark: str, labels: Sequence[BenchmarkLabel]) -> int:
        raise ConfigError("the database is not configured: WAREHOUSE_DB_URL and WAREHOUSE_DB_APP_PASSWORD are needed")


@dataclass(frozen=True)
class CorpusContainer:
    facade: CorpusFacade
    close: Callable[[], None]
    # A dataset path as the user typed it: a relative one is read below DATASETS_ROOT.
    resolve_dataset: Callable[[str], str]


def label_readers() -> Mapping[str, BenchmarkLabelReader]:
    """TODO(P6.2-2): the label readers of CryptoAPI-Bench and OWASP Benchmark are written once their label files have
    been seen (D-191, D-298h); a reader is not written from a guess. Until then no benchmark can be loaded."""
    return {}


def build_corpus_container(settings: CorpusSettings, *, configure_logs: bool = True) -> CorpusContainer:
    if configure_logs:
        configure_logging(settings.log_level, service="quancrypt-data")
    clock = SystemClock()
    files = LocalCorpusFiles(settings.corpus_root)
    listing = CsvCorpusListStore(settings.reference_dir / LIST_FILE)
    manifest = CsvManifestStore(settings.reports_dir / MANIFEST_FILE)
    analyzer_client = new_client(settings.analysis_timeout_s, settings.internal_token)
    ingest_client = new_client(settings.ingest_timeout_s, settings.internal_token)
    analyzer = HttpCodeAnalyzer(settings.analyzer_url, analyzer_client)
    sink = HttpEventSink(settings.ingest_url, ingest_client)
    hasher = HmacProjectKeyHasher(settings.anon_salt)
    projects = ProjectAnalyzer(analyzer, files, settings.analyzer_mount)
    database = Database(settings.database) if settings.database is not None else None
    labels = PostgresBenchmarkLabelStore(database, clock) if database is not None else _NoDatabase()
    facade = CorpusFacade(
        build_list=BuildCorpusListService(CsvMsrDatasetReader(), listing, SelectionPolicy()),
        clone=CloneCorpusService(
            listing, manifest, SubprocessGitRepository(settings.corpus_root, settings.git_timeout_s), files
        ),
        analyze=AnalyzeCorpusService(listing, manifest, projects, sink, hasher, clock),
        load_benchmark=LoadBenchmarksService(label_readers(), labels, files, projects, sink, hasher, clock),
        report=ReportCorpusService(listing, manifest, MarkdownReportWriter(settings.reports_dir / REPORT_FILE), clock),
    )

    def close() -> None:
        analyzer_client.close()
        ingest_client.close()
        if database is not None:
            database.close()

    def resolve_dataset(raw: str) -> str:
        if os.path.isabs(raw) or settings.datasets_root is None:
            return raw
        return str(settings.datasets_root / raw)

    return CorpusContainer(facade=facade, close=close, resolve_dataset=resolve_dataset)


def bootstrap(*, need_database: bool = False, configure_logs: bool = True) -> CorpusContainer:
    """The container for the process environment (the command line and the flows call this and nothing else). A flow
    passes `configure_logs=False`: Prefect owns the logging of a flow run."""
    return build_corpus_container(load_corpus_settings(need_database=need_database), configure_logs=configure_logs)
