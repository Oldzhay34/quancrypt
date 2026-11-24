"""Inbound ports of labelling (P7.1): export a batch, import the labels of a labeller, record resolutions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class LabelingError(Exception):
    """The command cannot run (unknown batch, existing batch, a file with problems). The message names no value of a
    row."""


@dataclass(frozen=True)
class RowIssue:
    row: int  # 0: the file as a whole
    reason: str


@dataclass(frozen=True)
class ExportCommand:
    batch: str
    output: Path
    size: int
    double: int
    seed: int


@dataclass(frozen=True)
class ExportResult:
    batch: str
    candidates: int
    sampled: int
    double: int
    with_context: int
    without_location: int
    context_unavailable: int
    output: Path


@dataclass(frozen=True)
class ImportCommand:
    batch: str
    labeler_role: str  # FIRST or SECOND
    source: Path
    report: Path
    disagreements: Path


@dataclass(frozen=True)
class ImportResult:
    batch: str
    labeler_role: str
    stored: int
    issues: tuple[RowIssue, ...]
    kappa: float | None
    pairs: int
    disagreements: int


@dataclass(frozen=True)
class ResolveCommand:
    batch: str
    source: Path
    report: Path


@dataclass(frozen=True)
class ResolveResult:
    batch: str
    stored: int
    issues: tuple[RowIssue, ...]
    open_disagreements: int


class ExportLabelBatchUseCase(Protocol):
    def execute(self, command: ExportCommand) -> ExportResult: ...


class ImportLabelsUseCase(Protocol):
    def execute(self, command: ImportCommand) -> ImportResult: ...


class ResolveDisagreementsUseCase(Protocol):
    def execute(self, command: ResolveCommand) -> ResolveResult: ...
