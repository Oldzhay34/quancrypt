from __future__ import annotations

from collections.abc import Mapping

from quancrypt_data.domain.corpus import AnalysisStatus, is_valid_benchmark_name
from quancrypt_data.domain.corpus_events import BENCHMARK_ANALYSIS, benchmark_identifier, build_events
from quancrypt_data.port.inbound.corpus import (
    LoadBenchmarkCommand,
    LoadBenchmarkResult,
    LoadBenchmarkUseCase,
    UnknownBenchmarkError,
)
from quancrypt_data.port.outbound.corpus import (
    BenchmarkLabelReader,
    BenchmarkLabelStore,
    CorpusFiles,
    EventSink,
    ProjectKeyHasher,
)
from quancrypt_data.port.outbound.system import Clock
from quancrypt_data.usecase.event_delivery import deliver
from quancrypt_data.usecase.project_analysis import ProjectAnalyzer


class LoadBenchmarksService(LoadBenchmarkUseCase):
    """Loads a benchmark: its own labels into the landing table, and its code through the analyzer into
    `benchmark_analysis` events (source `benchmark`). A benchmark without a label reader is refused: its label format
    has not been seen, and a reader is not written from a guess (D-191, D-298h)."""

    def __init__(
        self,
        readers: Mapping[str, BenchmarkLabelReader],
        labels: BenchmarkLabelStore,
        files: CorpusFiles,
        projects: ProjectAnalyzer,
        sink: EventSink,
        hasher: ProjectKeyHasher,
        clock: Clock,
    ) -> None:
        self._readers = readers
        self._labels = labels
        self._files = files
        self._projects = projects
        self._sink = sink
        self._hasher = hasher
        self._clock = clock

    def execute(self, command: LoadBenchmarkCommand) -> LoadBenchmarkResult:
        if not is_valid_benchmark_name(command.benchmark):
            raise UnknownBenchmarkError("the benchmark code is not valid")
        reader = self._readers.get(command.benchmark)
        if reader is None:
            raise UnknownBenchmarkError("no label reader for this benchmark")
        loaded = self._labels.replace(command.benchmark, reader.read(command.source))
        directory = self._files.copy_benchmark(command.source, command.benchmark)
        analysis = self._projects.analyze(directory)
        if analysis.status is not AnalysisStatus.ANALYZED:
            return LoadBenchmarkResult(loaded, analysis.status.value, 0, 0, 0, 0, 0, 0)
        key = self._hasher.key_for(benchmark_identifier(command.benchmark))
        events = build_events(BENCHMARK_ANALYSIS, key, analysis.units, self._clock.now(), benchmark=command.benchmark)
        delivery, _ = deliver(self._sink, events)
        return LoadBenchmarkResult(
            labels_loaded=loaded,
            analysis=analysis.status.value,
            units=len(analysis.units),
            findings_total=sum(len(u.findings) for u in analysis.units),
            events_sent=len(events),
            accepted=delivery.accepted,
            duplicate=delivery.duplicate,
            quarantined=delivery.quarantined,
        )
