"""Inbound port: `quancrypt open`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OpenBrowserCommand:
    path: str


@dataclass(frozen=True)
class OpenBrowserResult:
    address: str  # the web UI address without the token


class OpenBrowserUseCase(Protocol):
    def execute(self, command: OpenBrowserCommand) -> OpenBrowserResult:
        """Check the project is initialised and give the web UI address; no browser is started (D-279)."""
        ...
