"""Inbound port: `quancrypt status`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quancrypt_cli.port.inbound.service_status import ServiceStatus


@dataclass(frozen=True)
class StatusResult:
    services: tuple[ServiceStatus, ...]
    all_required_healthy: bool


class ReportStatusUseCase(Protocol):
    def execute(self) -> StatusResult:
        """The health of every service."""
        ...
