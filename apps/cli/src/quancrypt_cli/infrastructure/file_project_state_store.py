"""ProjectStateStore adapter: `.quancrypt/config.yaml` and `.quancrypt/session.token` in the user's project.

This is the only code that writes inside the user's project (D-272). Everything it writes stays in `.quancrypt/`, which
must be a real directory (never a symbolic link that could lead the write somewhere else).
"""

from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from quancrypt_cli.domain.errors import InvalidSessionTokenError
from quancrypt_cli.domain.project import ProjectConfig, ProjectKind
from quancrypt_cli.domain.session_token import SessionToken
from quancrypt_cli.port.outbound.errors import StateStoreError

STATE_DIR = ".quancrypt"
CONFIG_FILE = "config.yaml"
TOKEN_FILE = "session.token"  # noqa: S105 - a file name, not a secret
_MAX_CONFIG_BYTES = 16 * 1024


class FileProjectStateStore:
    """Implements ProjectStateStore."""

    def load_config(self, root: Path) -> ProjectConfig | None:
        path = root / STATE_DIR / CONFIG_FILE
        if (root / STATE_DIR).is_symlink() or path.is_symlink():
            raise StateStoreError("config.yaml must not be reached through a symbolic link")
        if not path.exists():
            return None
        try:
            if path.stat().st_size > _MAX_CONFIG_BYTES:
                raise StateStoreError("config.yaml is too large")
            data: Any = yaml.safe_load(path.read_text("utf-8"))
            return ProjectConfig(
                name=str(data["name"]),
                kind=ProjectKind(data["kind"]),
                created_at=datetime.fromisoformat(str(data["created_at"])),
                quancrypt_version=str(data["quancrypt_version"]),
            )
        except StateStoreError:
            raise
        except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError):
            raise StateStoreError("config.yaml is unreadable or malformed") from None

    def save_config(self, root: Path, config: ProjectConfig) -> None:
        document = {
            "name": config.name,
            "kind": config.kind.value,
            "created_at": config.created_at.isoformat(),
            "quancrypt_version": config.quancrypt_version,
        }
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        self._write(self._state_dir(root) / CONFIG_FILE, text, 0o644)

    def save_token(self, root: Path, token: SessionToken) -> bool:
        path = self._state_dir(root) / TOKEN_FILE
        self._write(path, token.value + "\n", 0o600)
        try:
            return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
        except OSError:
            return False

    def load_token(self, root: Path) -> SessionToken | None:
        path = root / STATE_DIR / TOKEN_FILE
        if path.is_symlink():
            raise StateStoreError("session.token must not be a symbolic link")
        try:
            return SessionToken(path.read_text("utf-8").strip())
        except FileNotFoundError:
            return None
        except (OSError, InvalidSessionTokenError):
            raise StateStoreError("session.token is unreadable or malformed") from None

    @staticmethod
    def _state_dir(root: Path) -> Path:
        directory = root / STATE_DIR
        if directory.is_symlink():
            raise StateStoreError(".quancrypt must not be a symbolic link")
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
        except OSError:
            raise StateStoreError(".quancrypt could not be created") from None
        if not directory.is_dir():
            raise StateStoreError(".quancrypt is not a directory")
        return directory

    @staticmethod
    def _write(path: Path, text: str, mode: int) -> None:
        """Write through a new file of the right mode and rename it over the old one: the file is never readable with
        wider permissions than `mode`, not even for a moment, and an old wider file is replaced, not reused."""
        if path.is_symlink():
            raise StateStoreError(f"{path.name} must not be a symbolic link")
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                os.fchmod(descriptor, mode)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(text)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            os.replace(temporary, path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise StateStoreError(f"{path.name} could not be written") from None
