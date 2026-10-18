"""Outbound port: the `.quancrypt/` directory in the user's project, the only place the CLI writes there (D-272)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from quancrypt_cli.domain.project import ProjectConfig
from quancrypt_cli.domain.session_token import SessionToken


class ProjectStateStore(Protocol):
    def load_config(self, root: Path) -> ProjectConfig | None:
        """The stored config, or None when the project was never initialised. Raises `StateStoreError` if unreadable."""
        ...

    def save_config(self, root: Path, config: ProjectConfig) -> None: ...

    def save_token(self, root: Path, token: SessionToken) -> bool:
        """Replace the token file. Returns True when the file is readable by its owner only (mode 600); False when
        the file system ignores permissions (a Windows drive in WSL), so that the CLI can say so."""
        ...

    def load_token(self, root: Path) -> SessionToken | None:
        """The stored token, or None when there is none."""
        ...
