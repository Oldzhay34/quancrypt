"""Outbound port of the scope data set (P7.1, D-32)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.scope import ScopeRecord


class ScopeDatasetError(Exception):
    """A line of the data set is not a scope record (the message names the line, never its text)."""


class ScopeDatasetFiles(Protocol):
    """JSON Lines files: one record per line, keys in a fixed order."""

    def read(self, path: Path) -> list[ScopeRecord]: ...

    def write(self, path: Path, records: Sequence[ScopeRecord]) -> None: ...
