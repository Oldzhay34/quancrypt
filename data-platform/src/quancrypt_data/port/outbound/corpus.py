"""Outbound ports of the corpus tooling (P6.2): everything the use cases need from the outside world, each one
narrow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from quancrypt_data.domain.corpus import Candidate, ManifestEntry, RepoRef, SelectedProject
from quancrypt_data.domain.corpus_events import TopologySummary, UnitAnalysis


class DatasetError(Exception):
    """The dataset file cannot be read as a project list. The message names columns, never data."""


class CloneError(Exception):
    """git could not clone the repository. The message never carries git's output."""


class AnalysisUnsupportedError(Exception):
    """The analyzer cannot analyse this root (422): not a Maven or Gradle project, or beyond its limits."""


class AnalysisFailedError(Exception):
    """The analyzer failed or could not be reached. The message names the status, never the answer."""


class EventDeliveryError(Exception):
    """ingest-api did not accept the events; they can be sent again (their ids are derived)."""


class DatasetReader(Protocol):
    def read(self, path: Path) -> Sequence[Candidate]: ...


class CorpusListStore(Protocol):
    """`reference/corpus_projects.csv`: repo_url, default_branch, license_spdx, selection_reason."""

    def write(self, projects: Sequence[SelectedProject]) -> None: ...

    def read(self) -> Sequence[RepoRef]:
        """The listed repositories in list order."""
        ...


class ManifestStore(Protocol):
    def load(self) -> Mapping[str, ManifestEntry]:
        """The entries by `repo_url` (canonical)."""
        ...

    def save(self, entries: Mapping[str, ManifestEntry]) -> None: ...


@dataclass(frozen=True)
class CloneResult:
    commit_sha: str
    default_branch: str


class GitRepository(Protocol):
    def clone(self, repo: RepoRef) -> CloneResult:
        """A shallow clone of the default branch into the corpus root; nothing from the repository is run."""
        ...


class CorpusFiles(Protocol):
    """The corpus root on disk. Names are the `dir_name` of a repository or a validated benchmark directory."""

    def exists(self, dir_name: str) -> bool: ...

    def read_license(self, dir_name: str) -> str | None:
        """The text of the license file of the clone, or None."""
        ...

    def has_spring_boot(self, dir_name: str) -> bool: ...

    def service_directories(self, dir_name: str, max_depth: int, limit: int) -> Sequence[str]:
        """Relative paths of the sub-directories (not the root) that hold a build file, sorted, at most `limit`."""
        ...

    def size_bytes(self) -> int:
        """The bytes the corpus root takes (clones and benchmark copies)."""
        ...

    def remove(self, dir_name: str) -> None: ...

    def copy_benchmark(self, source: Path, name: str) -> str:
        """Copies a benchmark's source tree below `_benchmarks/<name>` of the corpus root; returns that directory
        name."""
        ...


class CodeAnalyzer(Protocol):
    def analyze(self, root: str) -> UnitAnalysis:
        """Analyses `root` (a path as the analyzer sees it, under `/corpus`); the unit is `.`. Raises
        AnalysisUnsupportedError or AnalysisFailedError."""
        ...

    def topology(self, root: str) -> TopologySummary | None:
        """The topology summary, or None when the analyzer cannot build one for this root."""
        ...


@dataclass(frozen=True)
class DeliveryResult:
    accepted: int = 0
    duplicate: int = 0
    quarantined: int = 0
    superseded: int = 0
    consent_revoked: int = 0


class EventSink(Protocol):
    def send(self, events: Sequence[Mapping[str, object]]) -> DeliveryResult:
        """Delivers the events (at most 500) to ingest-api. Raises EventDeliveryError."""
        ...


class ProjectKeyHasher(Protocol):
    def key_for(self, identifier: str) -> str:
        """HMAC-SHA256 hex of the identifier with QUANCRYPT_ANON_SALT."""
        ...


class ReportWriter(Protocol):
    def write(self, text: str) -> str:
        """Writes `reports/corpus_run.md`; returns where."""
        ...


@dataclass(frozen=True)
class BenchmarkLabel:
    """One label of a benchmark's own ground truth, as the landing table keeps it (`raw.benchmark_label`)."""

    case_id: str
    file_path: str | None
    category: str | None
    cwe: int | None
    expected_vulnerable: bool


class BenchmarkLabelReader(Protocol):
    def read(self, source: Path) -> Sequence[BenchmarkLabel]: ...


class BenchmarkLabelStore(Protocol):
    def replace(self, benchmark: str, labels: Sequence[BenchmarkLabel]) -> int:
        """Deletes the labels of the benchmark and writes these, in one transaction; returns how many are written."""
        ...
