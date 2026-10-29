"""In-memory fakes of the corpus outbound ports that the use case tests and the port contract tests share (the same tests run
against these and against the real adapters, so a fake cannot drift from the port)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quancrypt_data.domain.corpus import ManifestEntry, RepoRef, SelectedProject
from quancrypt_data.domain.corpus_events import project_key
from quancrypt_data.port.outbound.corpus import BenchmarkLabel


class FakeListing:
    def __init__(self, repos: Sequence[RepoRef] = ()) -> None:
        self.repos = list(repos)
        self.written: list[SelectedProject] = []

    def write(self, projects: Sequence[SelectedProject]) -> None:
        self.written = list(projects)
        self.repos = [p.candidate.repo for p in projects]

    def read(self) -> Sequence[RepoRef]:
        return self.repos


class FakeManifest:
    def __init__(self) -> None:
        self.entries: dict[str, ManifestEntry] = {}
        self.saves = 0

    def load(self) -> Mapping[str, ManifestEntry]:
        return dict(self.entries)

    def save(self, entries: Mapping[str, ManifestEntry]) -> None:
        self.entries = dict(entries)
        self.saves += 1


class FakeHasher:
    def key_for(self, identifier: str) -> str:
        return project_key("k" * 40, identifier)


class FakeWriter:
    def __init__(self) -> None:
        self.text = ""

    def write(self, text: str) -> str:
        self.text = text
        return "reports/corpus_run.md"


class FakeLabels:
    def __init__(self) -> None:
        self.stored: dict[str, list[BenchmarkLabel]] = {}

    def replace(self, benchmark: str, labels: Sequence[BenchmarkLabel]) -> int:
        self.stored[benchmark] = list(labels)
        return len(labels)
