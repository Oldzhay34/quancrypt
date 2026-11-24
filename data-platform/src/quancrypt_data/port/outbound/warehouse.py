"""The ports of the warehouse build (P6.6): the dbt run and the lock that keeps an erasure and a build apart."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol


class WarehouseBusyError(Exception):
    """Another build holds the lock (or the lock could not be taken in time)."""


@dataclass(frozen=True)
class BuildOutcome:
    ok: bool
    built: Mapping[str, int]
    tests_passed: int
    tests_failed: int
    tests_warned: int
    skipped: int
    failed: Sequence[str]
    duration_s: float


class WarehouseBuilder(Protocol):
    def build(self) -> BuildOutcome:
        """Run the whole build (seeds, snapshots, models and their tests) and say what happened."""
        ...


class WarehouseBuildLock(Protocol):
    def held(self) -> AbstractContextManager[None]:
        """Hold the build lock for the length of the `with` block. ingest-api takes the same lock (as a transaction
        lock) before it erases rows of the warehouse tables, so an erasure waits for a build that runs and a build waits
        for an erasure that runs (D-319d). Raises WarehouseBusyError when the lock cannot be taken in time."""
        ...
