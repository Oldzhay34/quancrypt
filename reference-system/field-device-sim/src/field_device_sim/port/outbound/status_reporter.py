"""Outbound port: the status the container health check looks at (the simulator has no port to probe)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class StatusReporter(Protocol):
    """Remembers when the last transaction was published successfully."""

    def record_success(self, at: datetime) -> None:
        """Remember a successful publication."""
        ...

    def last_success(self) -> datetime | None:
        """The time of the last successful publication, or None when there is none or it cannot be read."""
        ...
