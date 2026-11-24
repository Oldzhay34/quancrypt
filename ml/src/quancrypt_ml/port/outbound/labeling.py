"""Outbound ports of the labelling use cases (P7.1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.labels import BatchRow, Candidate, LabelRecord, Resolution, SourceLocation


class LabelCandidateSource(Protocol):
    """The findings that can be labelled: marts.mart_risk_features (corpus and benchmark rows, D-317h)."""

    def candidates(self) -> list[Candidate]: ...

    def known(self, finding_ids: Sequence[str]) -> set[str]:
        """Which of the findings the warehouse still has."""
        ...


class SourceLocator(Protocol):
    """The real location of corpus findings (D-322b: the one recorded exception to "raw is not read" of ml-pipeline
    section 2). A finding without one (benchmark, user, a whole file) is left out of the result."""

    def locate(self, finding_ids: Sequence[str]) -> dict[str, SourceLocation]: ...


class SnippetUnavailableError(Exception):
    """The analyzer has no context for the location (the clone or the line is gone, the path is refused)."""


class AnalyzerUnavailableError(Exception):
    """The analyzer cannot be reached or answered with an error that is not about the location."""


class SnippetSource(Protocol):
    """Redacted lines around a location, from the analyzer (`get_snippet`; the analyzer redacts, D-179)."""

    def context(self, location: SourceLocation, radius: int) -> tuple[tuple[int, str], ...]: ...


@dataclass(frozen=True)
class NewBatch:
    id: str
    name: str
    created_at: datetime
    seed: int
    items: Sequence[tuple[str, str, bool]]  # (finding_id, project_key, double_label)


@dataclass(frozen=True)
class StoredBatch:
    id: str
    name: str
    size: int
    double_size: int
    items: Mapping[str, bool]  # finding_id -> double_label


class ResolutionConflictError(Exception):
    """A record to resolve is no longer a disagreement (its labels changed since they were read)."""


class BatchExistsError(Exception):
    """A batch of that name is already stored (an export is never repeated over an existing batch)."""


class LabelStore(Protocol):
    """warehouse_db.labels (ml/migrations). Every method is one transaction."""

    def create_batch(self, batch: NewBatch) -> None: ...

    def batch(self, name: str) -> StoredBatch | None: ...

    def replace_labels(self, batch_id: str, labeler_role: str, records: Sequence[LabelRecord], at: datetime) -> None:
        """The labels of one labeller of a batch, replaced as a whole (a re-import writes them again). In the same
        transaction, a resolution resolves a pair of labels: it is removed when the label of this labeller changed for
        its record or the two labels no longer differ (an old resolution must never override a new label)."""
        ...

    def labels(self, batch_id: str, labeler_role: str) -> dict[str, str]: ...

    def replace_resolutions(self, batch_id: str, resolutions: Sequence[Resolution], at: datetime) -> None:
        """Adds or replaces the given resolutions (the others stay). Every record must still be a disagreement when the
        resolutions are written (checked under the lock of the import): otherwise `ResolutionConflictError` and nothing
        is written."""
        ...

    def resolutions(self, batch_id: str) -> dict[str, str]: ...


class BatchFiles(Protocol):
    """The CSV files of a batch (git-ignored, D-322a)."""

    def write_batch(self, path: Path, rows: Sequence[BatchRow]) -> None: ...

    def read_rows(self, path: Path) -> list[dict[str, str]]: ...

    def write_rows(self, path: Path, rows: Sequence[Mapping[str, str]]) -> None: ...


class ReportWriter(Protocol):
    def write(self, path: Path, text: str) -> None: ...
