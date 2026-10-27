from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware (UTC)."""
        ...


class IdGenerator(Protocol):
    def new_id(self) -> UUID: ...
