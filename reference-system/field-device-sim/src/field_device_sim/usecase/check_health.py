"""Use case: judge the health of the simulator from its last successful publication."""

from __future__ import annotations

from field_device_sim.port.inbound.check_health import CheckHealthQuery, HealthResult
from field_device_sim.port.outbound.clock import Clock
from field_device_sim.port.outbound.status_reporter import StatusReporter


class CheckHealth:
    """Implements CheckHealthUseCase."""

    def __init__(self, clock: Clock, status: StatusReporter) -> None:
        self._clock = clock
        self._status = status

    def execute(self, query: CheckHealthQuery) -> HealthResult:
        last = self._status.last_success()
        if last is None:
            return HealthResult(False, "no successful publication yet")
        age = (self._clock.now() - last).total_seconds()
        if age > query.max_age_seconds:
            return HealthResult(False, f"last successful publication was {age:.0f} s ago")
        return HealthResult(True, f"last successful publication was {max(age, 0):.0f} s ago")
