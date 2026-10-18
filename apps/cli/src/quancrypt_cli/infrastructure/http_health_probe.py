"""HealthProbe adapter: one short HTTP GET to a local service."""

from __future__ import annotations

import httpx

from quancrypt_cli.domain.services import LOCAL_HOSTS, ServiceEndpoint, ServiceHealth

TIMEOUT_S = 2.0


class HttpHealthProbe:
    """Implements HealthProbe. Only loopback addresses are called (guardrails-security section 1)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        # `trust_env=False`: no proxy from the environment; no redirects are followed.
        self._client = client or httpx.Client(timeout=TIMEOUT_S, trust_env=False, follow_redirects=False)

    def check(self, endpoint: ServiceEndpoint) -> ServiceHealth:
        try:
            if httpx.URL(endpoint.url).host not in LOCAL_HOSTS:
                return ServiceHealth(endpoint.name, False, "not a local address")
            response = self._client.get(endpoint.url)
        except (httpx.HTTPError, httpx.InvalidURL):
            return ServiceHealth(endpoint.name, False, "not reachable")
        code = response.status_code
        healthy = code == 200 if endpoint.strict else code < 500
        return ServiceHealth(endpoint.name, healthy, f"HTTP {code}")
