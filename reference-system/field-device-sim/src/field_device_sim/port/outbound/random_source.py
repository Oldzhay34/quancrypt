"""Outbound port: random choices behind an interface so that tests are deterministic."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class RandomSource(Protocol):
    """Source of random choices."""

    def pick(self, options: Sequence[str]) -> str:
        """One of the options."""
        ...

    def integer(self, low: int, high: int) -> int:
        """An integer between low and high, both inclusive."""
        ...
