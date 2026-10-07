"""Random choices from the standard library generator."""

from __future__ import annotations

import random
from collections.abc import Sequence


class SystemRandomSource:
    """Implements RandomSource; pass a seeded random.Random for reproducible values."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()  # noqa: S311 - demo values, not secrets

    def pick(self, options: Sequence[str]) -> str:
        return self._rng.choice(options)

    def integer(self, low: int, high: int) -> int:
        return self._rng.randint(low, high)
