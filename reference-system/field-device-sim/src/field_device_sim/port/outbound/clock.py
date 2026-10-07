"""Outbound port: the current time."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime:
        """The current time as a timezone aware UTC datetime."""
        ...
