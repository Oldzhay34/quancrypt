"""ResolveDisagreements (P7.1): the user's resolution of the records the two labellers disagree on. The gold label of
such a record is the resolution (D-322d); a record without one keeps the first labeller's label until it is resolved."""

from __future__ import annotations

from quancrypt_ml.domain.labels import FIRST, SECOND, agreement, check_resolutions
from quancrypt_ml.port.inbound.labeling import LabelingError, ResolveCommand, ResolveResult, RowIssue
from quancrypt_ml.port.outbound.labeling import BatchFiles, LabelStore, ResolutionConflictError
from quancrypt_ml.port.outbound.system import Clock
from quancrypt_ml.usecase.labeling_report_writer import LabelingReporter


class ResolveDisagreementsService:
    def __init__(self, store: LabelStore, files: BatchFiles, reporter: LabelingReporter, clock: Clock) -> None:
        self._store = store
        self._files = files
        self._reporter = reporter
        self._clock = clock

    def execute(self, command: ResolveCommand) -> ResolveResult:
        batch = self._store.batch(command.batch)
        if batch is None:
            raise LabelingError(f"batch {command.batch} is not stored")
        first, second = self._store.labels(batch.id, FIRST), self._store.labels(batch.id, SECOND)
        if not set(first) & set(second):
            raise LabelingError("the batch has no double-labelled record yet (import both labellers first)")
        differ = {f: (x, y) for f, x, y in agreement(first, second).disagreements}
        resolutions, problems = check_resolutions(self._files.read_rows(command.source), differ)
        issues = tuple(RowIssue(p.row, p.reason) for p in problems)
        if issues:
            return ResolveResult(command.batch, 0, issues, len(differ) - len(self._store.resolutions(batch.id)))
        try:
            self._store.replace_resolutions(batch.id, resolutions, self._clock.now())
        except ResolutionConflictError:
            raise LabelingError("the labels changed while resolving; run label-resolve again") from None
        self._reporter.refresh(batch, command.report, None)
        open_count = len(set(differ) - set(self._store.resolutions(batch.id)))
        return ResolveResult(command.batch, len(resolutions), (), open_count)
