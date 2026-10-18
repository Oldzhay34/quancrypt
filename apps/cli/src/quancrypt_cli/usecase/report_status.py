"""Use case: `quancrypt status` shows the health of every service."""

from __future__ import annotations

from quancrypt_cli.domain.services import ALL_SERVICES
from quancrypt_cli.port.inbound.report_status import StatusResult
from quancrypt_cli.port.inbound.service_status import ServiceStatus
from quancrypt_cli.port.outbound.health_probe import HealthProbe


class ReportStatus:
    """Implements ReportStatusUseCase."""

    def __init__(self, probe: HealthProbe) -> None:
        self._probe = probe

    def execute(self) -> StatusResult:
        checked = [(endpoint, self._probe.check(endpoint)) for endpoint in ALL_SERVICES]
        services = tuple(ServiceStatus(health.name, health.healthy, health.detail) for _, health in checked)
        required_ok = all(health.healthy for endpoint, health in checked if endpoint.required)
        return StatusResult(services, required_ok)
