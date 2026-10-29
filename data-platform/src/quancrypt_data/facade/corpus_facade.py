"""The coarse entry point of the corpus command line and flows: commands from plain values, results as plain counts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from quancrypt_data.port.inbound.corpus import (
    AnalyzeCorpusCommand,
    AnalyzeCorpusUseCase,
    BuildCorpusListCommand,
    BuildCorpusListUseCase,
    CloneCorpusCommand,
    CloneCorpusUseCase,
    LoadBenchmarkCommand,
    LoadBenchmarkUseCase,
    ReportCorpusUseCase,
    UnknownBenchmarkError,
)

GIB = 1024**3


class BenchmarkNotAnalysedError(Exception):
    """The labels were loaded but the code of the benchmark could not be analysed (a non-zero exit, not a quiet
    zero)."""


class BenchmarkNotSupportedError(Exception):
    """No label reader exists for the benchmark (maps to a clear message and a non-zero exit)."""


@dataclass(frozen=True)
class StepView:
    """What a step did: named counts and free lines (never data of the analysed projects)."""

    counts: Mapping[str, int] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


class CorpusFacade:
    def __init__(
        self,
        build_list: BuildCorpusListUseCase,
        clone: CloneCorpusUseCase,
        analyze: AnalyzeCorpusUseCase,
        load_benchmark: LoadBenchmarkUseCase,
        report: ReportCorpusUseCase,
    ) -> None:
        self._build_list = build_list
        self._clone = clone
        self._analyze = analyze
        self._load_benchmark = load_benchmark
        self._report = report

    def build_list(self, dataset: str, size: int) -> StepView:
        result = self._build_list.execute(BuildCorpusListCommand(dataset=Path(dataset), size=size))
        rules = tuple(f"turned away by {rule}: {count}" for rule, count in result.turned_away.items())
        return StepView({"candidates": result.candidates, "selected": result.selected}, rules)

    def clone(self, offset: int, limit: int, max_disk_gb: float) -> StepView:
        result = self._clone.execute(
            CloneCorpusCommand(offset=offset, limit=limit, max_disk_bytes=int(max_disk_gb * GIB))
        )
        counts = {
            "attempted": result.attempted,
            "cloned": result.cloned,
            "already_there": result.already_there,
            "failed": result.failed,
            "excluded": sum(result.excluded.values()),
            "disk_mib": result.disk_bytes // (1024 * 1024),
        }
        notes = tuple(f"excluded ({reason}): {count}" for reason, count in result.excluded.items())
        if result.stopped_by_disk_limit:
            notes += ("stopped: the corpus root reached the disk limit",)
        return StepView(counts, notes)

    def analyze(self, offset: int, limit: int) -> StepView:
        result = self._analyze.execute(AnalyzeCorpusCommand(offset=offset, limit=limit))
        return StepView(
            {
                "attempted": result.attempted,
                "analyzed": result.analyzed,
                "unsupported": result.unsupported,
                "failed": result.failed,
                "findings_total": result.findings_total,
                "events_sent": result.events_sent,
                "accepted": result.accepted,
                "duplicate": result.duplicate,
                "quarantined": result.quarantined,
            }
        )

    def load_benchmark(self, benchmark: str, source: str) -> StepView:
        try:
            result = self._load_benchmark.execute(LoadBenchmarkCommand(benchmark=benchmark, source=Path(source)))
        except UnknownBenchmarkError as exc:
            raise BenchmarkNotSupportedError(str(exc)) from exc
        if result.analysis != "analyzed":
            raise BenchmarkNotAnalysedError(
                f"{result.labels_loaded} labels were loaded, but the code of the benchmark was not analysed "
                f"({result.analysis})"
            )
        return StepView(
            {
                "labels_loaded": result.labels_loaded,
                "units": result.units,
                "findings_total": result.findings_total,
                "events_sent": result.events_sent,
                "accepted": result.accepted,
                "duplicate": result.duplicate,
                "quarantined": result.quarantined,
            }
        )

    def report(self) -> StepView:
        result = self._report.execute()
        return StepView({"listed": result.listed, "analyzed": result.analyzed}, (f"report written: {result.path}",))
