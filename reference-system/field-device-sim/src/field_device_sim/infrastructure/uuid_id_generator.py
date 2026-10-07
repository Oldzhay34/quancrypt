"""Version 4 UUIDs, reproducible when a seeded random generator is given."""

from __future__ import annotations

import random
import uuid


class UuidIdGenerator:
    """Implements IdGenerator.

    Without a generator the identifiers come from uuid.uuid4(). With a seeded random.Random they are reproducible,
    which is meant for tests and demos only (the generator is not cryptographically secure).
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng

    def new_id(self) -> str:
        if self._rng is None:
            return str(uuid.uuid4())
        return str(uuid.UUID(int=self._rng.getrandbits(128), version=4))
