"""Outbound port: is a service answering?"""

from __future__ import annotations

from typing import Protocol

from quancrypt_cli.domain.services import ServiceEndpoint, ServiceHealth


class HealthProbe(Protocol):
    def check(self, endpoint: ServiceEndpoint) -> ServiceHealth:
        """One attempt; never raises: an unreachable service is an unhealthy `ServiceHealth`."""
        ...
