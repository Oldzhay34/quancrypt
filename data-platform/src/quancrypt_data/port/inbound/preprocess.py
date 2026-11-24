"""Use case Preprocess (P6.4): raw → filters → prep and the prep quarantine, then the report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PreprocessResult:
    written: Sequence[str]
    projects: int
    findings: int
    rows_in: int
    rows_rejected: int
    leaks: Mapping[str, int]
    quarantine_rate: float
    quarantine_warning: bool
    projects_target_met: bool
    findings_target_met: bool


class PreprocessUseCase(Protocol):
    def execute(self) -> PreprocessResult: ...
