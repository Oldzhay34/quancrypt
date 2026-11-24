"""ExportLabelBatch (P7.1, D-25, D-322): a stratified sample of the warehouse findings, written as the CSV a labeller
fills in, and stored as a batch so that the import can check the labels against it."""

from __future__ import annotations

from quancrypt_ml.domain.labels import (
    CONTEXT_NO_LOCATION,
    CONTEXT_OK,
    CONTEXT_RADIUS,
    CONTEXT_UNAVAILABLE,
    BatchRow,
    stratified_sample,
)
from quancrypt_ml.port.inbound.labeling import ExportCommand, ExportResult, LabelingError
from quancrypt_ml.port.outbound.labeling import (
    AnalyzerUnavailableError,
    BatchExistsError,
    BatchFiles,
    LabelCandidateSource,
    LabelStore,
    NewBatch,
    SnippetSource,
    SnippetUnavailableError,
    SourceLocator,
)
from quancrypt_ml.port.outbound.system import Clock, IdGenerator


class ExportLabelBatchService:
    # Seven collaborators, one per port (ISP): the sample, the location, the context, the batch, the file and time.
    def __init__(
        self,
        candidates: LabelCandidateSource,
        locator: SourceLocator,
        snippets: SnippetSource,
        store: LabelStore,
        files: BatchFiles,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._candidates = candidates
        self._locator = locator
        self._snippets = snippets
        self._store = store
        self._files = files
        self._clock = clock
        self._ids = ids

    def execute(self, command: ExportCommand) -> ExportResult:
        if command.double > command.size:
            raise LabelingError("the double-label count cannot exceed the sample size")
        if self._store.batch(command.batch) is not None:
            raise LabelingError(f"batch {command.batch} already exists; a batch is exported once")
        pool = self._candidates.candidates()
        sample = stratified_sample(pool, command.size, command.double, command.seed)
        if not sample:
            raise LabelingError("the warehouse has no finding to label (run preprocess and the warehouse build first)")
        locations = self._locator.locate([s.candidate.finding_id for s in sample])
        rows: list[BatchRow] = []
        for sampled in sample:
            location = locations.get(sampled.candidate.finding_id)
            if location is None or location.line is None:
                rows.append(BatchRow(sampled, location, (), CONTEXT_NO_LOCATION))
                continue
            try:
                context = self._snippets.context(location, CONTEXT_RADIUS)
            except AnalyzerUnavailableError:
                # Nothing is stored yet: the export can simply be run again once the analyzer is up.
                raise LabelingError("the analyzer cannot be reached (start the app profile with CORPUS_ROOT)") from None
            except SnippetUnavailableError:
                rows.append(BatchRow(sampled, location, (), CONTEXT_UNAVAILABLE))
            else:
                rows.append(BatchRow(sampled, location, context, CONTEXT_OK))
        batch = NewBatch(
            id=self._ids.new_id(),
            name=command.batch,
            created_at=self._clock.now(),
            seed=command.seed,
            items=[(s.candidate.finding_id, s.candidate.project_key, s.double_label) for s in sample],
        )
        try:
            self._store.create_batch(batch)
        except BatchExistsError:
            raise LabelingError(f"batch {command.batch} already exists; a batch is exported once") from None
        # The file is written after the batch is stored: a file whose batch is missing could not be imported.
        self._files.write_batch(command.output, rows)
        statuses = [r.context_status for r in rows]
        return ExportResult(
            batch=command.batch,
            candidates=len(pool),
            sampled=len(sample),
            double=sum(s.double_label for s in sample),
            with_context=statuses.count(CONTEXT_OK),
            without_location=statuses.count(CONTEXT_NO_LOCATION),
            context_unavailable=statuses.count(CONTEXT_UNAVAILABLE),
            output=command.output,
        )
