"""CoreApiClient adapter: `POST /api/v1/projects` of core-service with the session token (Bearer)."""

from __future__ import annotations

import uuid

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from quancrypt_cli.domain.services import LOCAL_HOSTS
from quancrypt_cli.domain.session_token import SessionToken
from quancrypt_cli.port.outbound.core_api_client import RegisteredProject
from quancrypt_cli.port.outbound.errors import CoreApiError

ATTEMPTS = 3
TIMEOUT_S = 10.0


class HttpCoreApiClient:
    """Implements CoreApiClient. Repeating the call is safe: it carries an `Idempotency-Key` and core answers 200 for
    an identity it already knows (D-129). Only connection failures are retried."""

    def __init__(self, base_url: str, client: httpx.Client | None = None, retry_wait_s: float = 1.0) -> None:
        url = httpx.URL(base_url)
        if url.host not in LOCAL_HOSTS:
            raise ValueError("core-service must be a local address")
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=TIMEOUT_S, trust_env=False, follow_redirects=False)
        self._retry_wait_s = retry_wait_s

    def register_project(self, token: SessionToken, identity: str, display_name: str) -> RegisteredProject:
        headers = {
            "Authorization": f"Bearer {token.value}",
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Trace-Id": uuid.uuid4().hex,
        }
        body = {"identity": identity, "displayName": display_name}
        retrying = Retrying(
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            stop=stop_after_attempt(ATTEMPTS),
            wait=wait_fixed(self._retry_wait_s),
            reraise=True,
        )
        try:
            response = retrying(
                lambda: self._client.post(f"{self._base_url}/api/v1/projects", headers=headers, json=body)
            )
        except httpx.HTTPError:
            raise CoreApiError("unreachable") from None
        if response.status_code in (200, 201):
            try:
                project_id = str(response.json()["id"])
                uuid.UUID(project_id)
            except (ValueError, KeyError, TypeError):
                raise CoreApiError("rejected", response.status_code) from None
            return RegisteredProject(project_id, created=response.status_code == 201)
        if response.status_code in (401, 403):
            raise CoreApiError("unauthorized", response.status_code)
        raise CoreApiError("rejected", response.status_code)
