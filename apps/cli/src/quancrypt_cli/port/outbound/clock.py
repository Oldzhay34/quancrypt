"""Outbound port: time, for the creation stamp and the readiness wait."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time as a timezone aware UTC datetime."""
        ...

    def monotonic(self) -> float:
        """Seconds on a clock that never goes back (for deadlines)."""
        ...

    def sleep(self, seconds: float) -> None: ...
