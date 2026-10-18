"""FileSystem adapter: read-only access to the user's project."""

from __future__ import annotations

from pathlib import Path


class LocalFileSystem:
    """Implements FileSystem."""

    def absolute(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    def is_directory(self, path: Path) -> bool:
        return path.is_dir()

    def entries(self, path: Path) -> frozenset[str]:
        return frozenset(entry.name for entry in path.iterdir())

    def read_lines(self, path: Path) -> list[str] | None:
        try:
            return path.read_text("utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return None
        except (IsADirectoryError, PermissionError):
            return None
