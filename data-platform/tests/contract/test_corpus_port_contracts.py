"""Contract tests of the corpus outbound ports (solid-checklist L): the same tests run against the in-memory fake the use case
tests use and against the real adapter, so a fake cannot promise what the adapter does not do. Ports with a single behaviour
worth fixing here are covered; the git, analyzer and event-sink adapters have their own tests in `test_corpus_adapters.py`
(they need a repository, a fake HTTP server or a clock to set up, which the fake does not share)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from quancrypt_data.domain.corpus import (
    AnalysisStatus,
    Candidate,
    CloneStatus,
    ExclusionReason,
    ManifestEntry,
    RepoRef,
    SelectedProject,
)
from quancrypt_data.infrastructure.corpus.csv_stores import CsvCorpusListStore, CsvManifestStore, MarkdownReportWriter
from quancrypt_data.infrastructure.corpus.hasher import HmacProjectKeyHasher
from quancrypt_data.port.outbound.corpus import (
    BenchmarkLabel,
    CorpusListStore,
    ManifestStore,
    ProjectKeyHasher,
    ReportWriter,
)
from tests.support.corpus_fakes import FakeHasher, FakeLabels, FakeListing, FakeManifest, FakeWriter


def repo(name: str) -> RepoRef:
    return RepoRef.parse(f"https://github.com/acme/{name}")


class FakeWriterAdapter:
    """The report writer fake, with a way to read back what was written (a real writer is read from its file)."""

    def __init__(self) -> None:
        self._writer = FakeWriter()

    def write(self, text: str) -> str:
        return self._writer.write(text)

    @property
    def text(self) -> str:
        return self._writer.text


@pytest.fixture(params=["fake", "csv"])
def manifest(request: pytest.FixtureRequest, tmp_path: Path) -> ManifestStore:
    return FakeManifest() if request.param == "fake" else CsvManifestStore(tmp_path / "corpus_manifest.csv")


@pytest.fixture(params=["fake", "csv"])
def listing(request: pytest.FixtureRequest, tmp_path: Path) -> CorpusListStore:
    return FakeListing() if request.param == "fake" else CsvCorpusListStore(tmp_path / "corpus_projects.csv")


@pytest.fixture(params=["fake", "hmac"])
def hasher(request: pytest.FixtureRequest) -> ProjectKeyHasher:
    return FakeHasher() if request.param == "fake" else HmacProjectKeyHasher("s" * 40)


class TestManifestStore:
    def entry(self, name: str, **fields: object) -> ManifestEntry:
        return ManifestEntry(repo(name).url, **fields)  # type: ignore[arg-type]

    def test_nothing_is_loaded_before_anything_is_saved(self, manifest: ManifestStore) -> None:
        assert dict(manifest.load()) == {}

    def test_what_is_saved_is_what_is_loaded_by_the_canonical_address(self, manifest: ManifestStore) -> None:
        entries = {
            repo("a").canonical: self.entry(
                "a",
                status=CloneStatus.CLONED,
                commit_sha="f" * 40,
                license_verified="MIT",
                analysis_status=AnalysisStatus.ANALYZED,
                findings_total=7,
                units=2,
                analyzed_at="2026-10-28T09:30:00Z",
            ),
            repo("b").canonical: self.entry(
                "b", status=CloneStatus.EXCLUDED, exclusion_reason=ExclusionReason.NO_SPRING_BOOT
            ),
        }

        manifest.save(entries)

        assert dict(manifest.load()) == entries

    def test_saving_again_replaces_the_whole_content(self, manifest: ManifestStore) -> None:
        manifest.save({repo("a").canonical: self.entry("a"), repo("b").canonical: self.entry("b")})

        manifest.save({repo("b").canonical: self.entry("b")})

        assert set(manifest.load()) == {repo("b").canonical}


class TestCorpusListStore:
    def projects(self, *names: str) -> list[SelectedProject]:
        return [SelectedProject(Candidate(repo(n), None, None, None, None), "reason") for n in names]

    def test_a_list_that_was_never_written_is_empty(self, listing: CorpusListStore) -> None:
        assert list(listing.read()) == []

    def test_the_repositories_come_back_in_the_order_they_were_written(self, listing: CorpusListStore) -> None:
        listing.write(self.projects("c", "a", "b"))

        assert [r.name for r in listing.read()] == ["c", "a", "b"]

    def test_writing_again_replaces_the_list(self, listing: CorpusListStore) -> None:
        listing.write(self.projects("a", "b", "c"))

        listing.write(self.projects("z"))

        assert [r.name for r in listing.read()] == ["z"]


class TestReportWriter:
    @pytest.fixture(params=["fake", "markdown"])
    def writer_and_reader(
        self, request: pytest.FixtureRequest, tmp_path: Path
    ) -> Iterator[tuple[ReportWriter, Callable[[], str]]]:
        if request.param == "fake":
            fake = FakeWriterAdapter()
            yield fake, lambda: fake.text
        else:
            path = tmp_path / "reports" / "corpus_run.md"
            yield MarkdownReportWriter(path), lambda: path.read_text(encoding="utf-8")

    def test_the_text_is_written_as_it_is_and_the_place_is_returned(
        self, writer_and_reader: tuple[ReportWriter, Callable[[], str]]
    ) -> None:
        writer, read = writer_and_reader

        place = writer.write("# Rapor\n\nİçerik\n")

        assert read() == "# Rapor\n\nİçerik\n"
        assert place

    def test_a_second_write_replaces_the_first(self, writer_and_reader: tuple[ReportWriter, Callable[[], str]]) -> None:
        writer, read = writer_and_reader
        writer.write("first")

        writer.write("second")

        assert read() == "second"


class TestProjectKeyHasher:
    def test_a_key_is_64_lower_case_hex_digits(self, hasher: ProjectKeyHasher) -> None:
        key = hasher.key_for("corpus:https://github.com/acme/shop")

        assert len(key) == 64 and set(key) <= set("0123456789abcdef")

    def test_the_same_identifier_gives_the_same_key_and_another_gives_another(self, hasher: ProjectKeyHasher) -> None:
        assert hasher.key_for("x") == hasher.key_for("x")
        assert hasher.key_for("x") != hasher.key_for("y")


class TestBenchmarkLabelStoreFake:
    """The PostgreSQL adapter's side of this contract (replace and count, reload, failed load keeps the old labels) is in
    tests/integration/test_corpus_postgres.py (`TestBenchmarkLabels`); the fake must give the same answers to the cases that
    do not need a database."""

    def labels(self, n: int) -> list[BenchmarkLabel]:
        return [BenchmarkLabel(f"c{i}", None, None, None, True) for i in range(n)]

    def test_replace_returns_how_many_labels_are_now_stored(self) -> None:
        store = FakeLabels()

        assert store.replace("owasp-benchmark", self.labels(5)) == 5
        assert store.replace("owasp-benchmark", self.labels(2)) == 2
        assert len(store.stored["owasp-benchmark"]) == 2

    def test_a_benchmark_is_replaced_without_touching_another(self) -> None:
        store = FakeLabels()
        store.replace("owasp-benchmark", self.labels(3))
        store.replace("cryptoapi-bench", self.labels(1))

        store.replace("owasp-benchmark", [])

        assert (len(store.stored["owasp-benchmark"]), len(store.stored["cryptoapi-bench"])) == (0, 1)
