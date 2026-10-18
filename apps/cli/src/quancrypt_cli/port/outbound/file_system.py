"""Outbound port: read-only look at the user's project directory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileSystem(Protocol):
    """The CLI only reads the user's project here; it writes nowhere but `.quancrypt/` (ProjectStateStore, D-272)."""

    def absolute(self, path: str) -> Path:
        """The absolute, normalised path (symbolic links resolved)."""
        ...

    def is_directory(self, path: Path) -> bool: ...

    def entries(self, path: Path) -> frozenset[str]:
        """The names directly inside the directory."""
        ...

    def read_lines(self, path: Path) -> list[str] | None:
        """The lines of a text file, or None when it does not exist."""
        ...
