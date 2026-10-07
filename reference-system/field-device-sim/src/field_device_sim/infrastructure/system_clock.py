"""Clock backed by the system time."""

from __future__ import annotations

from datetime import datetime, timezone


class SystemClock:
    """Implements Clock."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
