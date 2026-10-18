"""Inbound port: `quancrypt init` (FR-01, FR-02)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quancrypt_cli.port.inbound.service_status import ServiceStatus


@dataclass(frozen=True)
class InitProjectCommand:
    path: str
    wait_timeout_s: int


@dataclass(frozen=True)
class InitProjectResult:
    project_name: str
    kind: str  # `maven` or `gradle`
    project_id: str
    newly_registered: bool
    token_renewed: bool  # a second `init` makes a new token (D-273)
    token_protected: bool  # the token file is mode 600; False on a file system that ignores permissions
    services: tuple[ServiceStatus, ...]
    gitignore_covers: bool  # `.quancrypt/` is already ignored by the user's `.gitignore` (D-272)
    gitignore_line: str  # the line to advise when it is not
    ui_address: str  # the web UI address without the token


class InitProjectUseCase(Protocol):
    def execute(self, command: InitProjectCommand) -> InitProjectResult:
        """Set the project up. Raises the errors of `port.inbound.errors`."""
        ...
