"""Use cases of the corpus tooling (P6.2): build the list, clone, analyse, load benchmarks, report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BuildCorpusListCommand:
    dataset: Path
    size: int


@dataclass(frozen=True)
class BuildCorpusListResult:
    candidates: int
    selected: int
    # Why the dataset ruled candidates out, by rule code.
    turned_away: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CloneCorpusCommand:
    offset: int
    limit: int
    max_disk_bytes: int


@dataclass(frozen=True)
class CloneCorpusResult:
    attempted: int
    cloned: int
    already_there: int
    excluded: dict[str, int] = field(default_factory=dict)
    failed: int = 0
    stopped_by_disk_limit: bool = False
    disk_bytes: int = 0


@dataclass(frozen=True)
class AnalyzeCorpusCommand:
    offset: int
    limit: int


@dataclass(frozen=True)
class AnalyzeCorpusResult:
    attempted: int
    analyzed: int
    unsupported: int
    failed: int
    findings_total: int
    events_sent: int
    accepted: int
    duplicate: int
    quarantined: int


@dataclass(frozen=True)
class LoadBenchmarkCommand:
    benchmark: str
    source: Path


@dataclass(frozen=True)
class LoadBenchmarkResult:
    labels_loaded: int
    # `analyzed`, `unsupported` or `failed`: what became of the analysis of the benchmark code (the labels are
    # loaded anyway).
    analysis: str
    units: int
    findings_total: int
    events_sent: int
    accepted: int
    duplicate: int
    quarantined: int


@dataclass(frozen=True)
class ReportCorpusResult:
    path: str
    listed: int
    analyzed: int


class UnknownBenchmarkError(Exception):
    """No label reader is available for the benchmark (its label format has not been seen yet)."""


class BuildCorpusListUseCase(Protocol):
    def execute(self, command: BuildCorpusListCommand) -> BuildCorpusListResult: ...


class CloneCorpusUseCase(Protocol):
    def execute(self, command: CloneCorpusCommand) -> CloneCorpusResult: ...


class AnalyzeCorpusUseCase(Protocol):
    def execute(self, command: AnalyzeCorpusCommand) -> AnalyzeCorpusResult: ...


class LoadBenchmarkUseCase(Protocol):
    def execute(self, command: LoadBenchmarkCommand) -> LoadBenchmarkResult: ...


class ReportCorpusUseCase(Protocol):
    def execute(self) -> ReportCorpusResult: ...
