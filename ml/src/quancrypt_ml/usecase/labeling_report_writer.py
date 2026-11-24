"""The report and the disagreement file of a batch, rebuilt from the stored labels after every import and resolution."""

from __future__ import annotations

from pathlib import Path

from quancrypt_ml.domain.labeling_report import LabelingStats, build_report, disagreement_rows
from quancrypt_ml.domain.labels import FIRST, SECOND, Agreement, agreement
from quancrypt_ml.port.outbound.labeling import (
    BatchFiles,
    LabelCandidateSource,
    LabelStore,
    ReportWriter,
    StoredBatch,
)


class LabelingReporter:
    def __init__(
        self, store: LabelStore, candidates: LabelCandidateSource, files: BatchFiles, reports: ReportWriter
    ) -> None:
        self._store = store
        self._candidates = candidates
        self._files = files
        self._reports = reports

    def refresh(self, batch: StoredBatch, report: Path, disagreements: Path | None) -> Agreement | None:
        first = self._store.labels(batch.id, FIRST)
        second = self._store.labels(batch.id, SECOND)
        resolved = self._store.resolutions(batch.id)
        result = agreement(first, second) if set(first) & set(second) else None
        labelled = sorted(set(first) | set(second))
        unmatched = len(set(labelled) - self._candidates.known(labelled))
        stats = LabelingStats(batch.name, batch.size, batch.double_size, first, second, resolved, result, unmatched)
        self._reports.write(report, build_report(stats))
        if result is not None and disagreements is not None:
            self._files.write_rows(disagreements, disagreement_rows(result, resolved))
        return result
