"""Inbound port: `quancrypt down`."""

from __future__ import annotations

from typing import Protocol


class StopServicesUseCase(Protocol):
    def execute(self) -> None:
        """Stop the services (volumes stay)."""
        ...
