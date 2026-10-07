"""Status kept in a small file that the container health check reads."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


class FileStatusReporter:
    """Implements StatusReporter: the file holds the time of the last successful publication as ISO 8601 UTC text."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def record_success(self, at: datetime) -> None:
        temporary = self._path.with_name(self._path.name + ".tmp")
        temporary.write_text(at.astimezone(timezone.utc).isoformat(), encoding="utf-8")
        os.replace(temporary, self._path)

    def last_success(self) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(self._path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        if parsed.tzinfo is None:
            return None
        return parsed
