"""Outbound port: the user's web browser."""

from __future__ import annotations

from typing import Protocol


class BrowserOpener(Protocol):
    def open(self, url: str) -> bool:
        """Ask the desktop to open the URL. False when no browser could be started."""
        ...
