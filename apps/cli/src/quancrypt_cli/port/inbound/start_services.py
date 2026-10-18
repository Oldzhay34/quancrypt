"""Inbound port: `quancrypt up`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quancrypt_cli.port.inbound.service_status import ServiceStatus


@dataclass(frozen=True)
class StartServicesCommand:
    path: str
    wait_timeout_s: int


@dataclass(frozen=True)
class StartServicesResult:
    services: tuple[ServiceStatus, ...]


class StartServicesUseCase(Protocol):
    def execute(self, command: StartServicesCommand) -> StartServicesResult:
        """Start the services for an initialised project with its stored token."""
        ...
