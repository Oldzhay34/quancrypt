"""Inbound port: is the simulator publishing?"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CheckHealthQuery:
    """The longest accepted time since the last successful publication, in seconds."""

    max_age_seconds: float


@dataclass(frozen=True)
class HealthResult:
    """Healthy or not, and why."""

    healthy: bool
    reason: str


class CheckHealthUseCase(Protocol):
    """Judges the health of the simulator from its last successful publication."""

    def execute(self, query: CheckHealthQuery) -> HealthResult:
        """Healthy when the last successful publication is not older than the maximum age."""
        ...
