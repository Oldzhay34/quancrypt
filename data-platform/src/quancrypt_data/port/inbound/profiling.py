"""Use case ProfileRawData (P6.3): profile the landing layer without changing it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProfileRawDataResult:
    written: Sequence[str]
    sources: int
    findings: int
    projects: int
    unmapped: int
    recommendations: int
    # True when every raw table had the same row count and digest before and after the profiling.
    unchanged: bool


class ProfileRawDataUseCase(Protocol):
    def execute(self) -> ProfileRawDataResult: ...
