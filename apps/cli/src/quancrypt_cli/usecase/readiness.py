"""Waiting for the backend services to answer their readiness endpoints."""

from __future__ import annotations

from quancrypt_cli.domain.services import BACKEND_SERVICES, ServiceHealth
from quancrypt_cli.port.inbound.errors import ServicesNotReadyError
from quancrypt_cli.port.outbound.clock import Clock
from quancrypt_cli.port.outbound.health_probe import HealthProbe

POLL_INTERVAL_S = 2.0


class ReadinessWaiter:
    """Polls core, analyzer and agent until all are ready or the time is up."""

    def __init__(self, probe: HealthProbe, clock: Clock, interval_s: float = POLL_INTERVAL_S) -> None:
        self._probe = probe
        self._clock = clock
        self._interval_s = interval_s

    def wait(self, timeout_s: int) -> tuple[ServiceHealth, ...]:
        deadline = self._clock.monotonic() + timeout_s
        while True:
            health = tuple(self._probe.check(endpoint) for endpoint in BACKEND_SERVICES)
            if all(item.healthy for item in health):
                return health
            if self._clock.monotonic() >= deadline:
                raise ServicesNotReadyError(tuple(item.name for item in health if not item.healthy))
            self._clock.sleep(self._interval_s)
