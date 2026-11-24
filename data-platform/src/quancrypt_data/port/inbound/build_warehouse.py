"""Use case BuildWarehouse (P6.6): dbt builds the warehouse from prep (seeds, snapshots, models, tests), while the build
lock is held."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BuildWarehouseResult:
    ok: bool
    # What dbt built, by kind: seed, snapshot, model.
    built: Mapping[str, int]
    tests_passed: int
    tests_failed: int
    tests_warned: int
    skipped: int
    # The nodes that failed (dbt unique ids: package and model names only), at most a few dozen.
    failed: Sequence[str]
    duration_s: float


class BuildWarehouseUseCase(Protocol):
    def execute(self) -> BuildWarehouseResult: ...
