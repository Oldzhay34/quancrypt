"""The entry point of the ml command line (hexagonal-service section 1): builds the commands, calls the use cases and
hands back plain views. It knows only the inbound ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quancrypt_ml.port.inbound.labeling import (
    ExportCommand,
    ExportLabelBatchUseCase,
    ExportResult,
    ImportCommand,
    ImportLabelsUseCase,
    ImportResult,
    LabelingError,
    ResolveCommand,
    ResolveDisagreementsUseCase,
    ResolveResult,
)
from quancrypt_ml.port.inbound.scope import ScopeSplitError, SplitCommand, SplitResult, SplitScopeDatasetUseCase


class MlCommandError(Exception):
    """A command that cannot run; the message is safe to print (no row value, no secret)."""


@dataclass(frozen=True)
class LabelPaths:
    """Where the files of a batch live: <labeling>/<batch>.csv, <batch>_second.csv, <batch>_disagreements.csv and the
    report."""

    labeling_dir: Path
    report: Path

    def batch(self, name: str) -> Path:
        return self.labeling_dir / f"{name}.csv"

    def disagreements(self, name: str) -> Path:
        return self.labeling_dir / f"{name}_disagreements.csv"


class LabelingFacade:
    def __init__(
        self,
        export: ExportLabelBatchUseCase,
        import_labels: ImportLabelsUseCase,
        resolve: ResolveDisagreementsUseCase,
        paths: LabelPaths,
    ) -> None:
        self._export = export
        self._import = import_labels
        self._resolve = resolve
        self._paths = paths

    def export_batch(self, batch: str, size: int, double: int, seed: int) -> ExportResult:
        try:
            return self._export.execute(ExportCommand(batch, self._paths.batch(batch), size, double, seed))
        except LabelingError as error:
            raise MlCommandError(str(error)) from None

    def import_labels(self, batch: str, labeler_role: str, source: Path) -> ImportResult:
        command = ImportCommand(batch, labeler_role, source, self._paths.report, self._paths.disagreements(batch))
        try:
            return self._import.execute(command)
        except LabelingError as error:
            raise MlCommandError(str(error)) from None

    def resolve(self, batch: str, source: Path | None) -> ResolveResult:
        command = ResolveCommand(batch, source or self._paths.disagreements(batch), self._paths.report)
        try:
            return self._resolve.execute(command)
        except LabelingError as error:
            raise MlCommandError(str(error)) from None


class ScopeFacade:
    def __init__(self, split: SplitScopeDatasetUseCase) -> None:
        self._split = split

    def split(self, dataset: Path, output_dir: Path, test_copy: Path, seed: int) -> SplitResult:
        try:
            return self._split.execute(SplitCommand(dataset, output_dir, test_copy, seed))
        except ScopeSplitError as error:
            raise MlCommandError("the scope data set is not valid: " + "; ".join(error.problems[:10])) from None
