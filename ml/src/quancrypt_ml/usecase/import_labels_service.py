"""ImportLabels (P7.1): the filled-in CSV of one labeller is checked as a whole and, only when every row is valid,
stored in one transaction (a re-import replaces the labeller's labels). The report and, once both labellers are in, the
disagreement file are rebuilt."""

from __future__ import annotations

from quancrypt_ml.domain.labels import LABELERS, check_labels
from quancrypt_ml.port.inbound.labeling import ImportCommand, ImportResult, LabelingError, RowIssue
from quancrypt_ml.port.outbound.labeling import BatchFiles, LabelStore
from quancrypt_ml.port.outbound.system import Clock
from quancrypt_ml.usecase.labeling_report_writer import LabelingReporter


class ImportLabelsService:
    def __init__(self, store: LabelStore, files: BatchFiles, reporter: LabelingReporter, clock: Clock) -> None:
        self._store = store
        self._files = files
        self._reporter = reporter
        self._clock = clock

    def execute(self, command: ImportCommand) -> ImportResult:
        if command.labeler_role not in LABELERS:
            raise LabelingError("the labeller is FIRST or SECOND")
        batch = self._store.batch(command.batch)
        if batch is None:
            raise LabelingError(f"batch {command.batch} is not stored (export it first)")
        records, problems = check_labels(self._files.read_rows(command.source), batch.items, command.labeler_role)
        issues = tuple(RowIssue(p.row, p.reason) for p in problems)
        if issues:
            # Nothing is stored from a file with problems: a half-imported labelling would skew kappa without a word.
            return ImportResult(command.batch, command.labeler_role, 0, issues, None, 0, 0)
        self._store.replace_labels(batch.id, command.labeler_role, records, self._clock.now())
        result = self._reporter.refresh(batch, command.report, command.disagreements)
        return ImportResult(
            batch=command.batch,
            labeler_role=command.labeler_role,
            stored=len(records),
            issues=(),
            kappa=None if result is None else result.kappa,
            pairs=0 if result is None else result.pairs,
            disagreements=0 if result is None else len(result.disagreements),
        )
