"""Outbound port: the Docker Compose stack of the Quancrypt installation (`app` profile)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from quancrypt_cli.domain.session_token import SessionToken


class ComposeRunner(Protocol):
    def up(self, project_root: Path, token: SessionToken, wait_timeout_s: int) -> None:
        """Start the services with PROJECT_ROOT and QUANCRYPT_SESSION_TOKEN and wait until their containers are
        healthy. Raises `ComposeError`."""
        ...

    def down(self) -> None:
        """Stop the services (volumes stay). Raises `ComposeError`."""
        ...
