"""Coarse-grained entry point of the simulator for the CLI: health."""

from __future__ import annotations

from dataclasses import dataclass

from field_device_sim.port.inbound.check_health import CheckHealthQuery, CheckHealthUseCase


@dataclass(frozen=True)
class HealthView:
    """The health of the simulator as the CLI shows it."""

    healthy: bool
    reason: str


class HealthFacade:
    """Answers whether the simulator is publishing."""

    def __init__(self, check: CheckHealthUseCase) -> None:
        self._check = check

    def health(self, max_age_seconds: float) -> HealthView:
        result = self._check.execute(CheckHealthQuery(max_age_seconds))
        return HealthView(result.healthy, result.reason)
