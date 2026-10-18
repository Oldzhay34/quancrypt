"""Starting the services and waiting for them; `init` and `up` share it."""

from __future__ import annotations

from pathlib import Path

from quancrypt_cli.domain.services import ServiceHealth
from quancrypt_cli.domain.session_token import SessionToken
from quancrypt_cli.port.inbound.errors import ComposeFailedError
from quancrypt_cli.port.outbound.compose_runner import ComposeRunner
from quancrypt_cli.port.outbound.errors import ComposeError
from quancrypt_cli.usecase.readiness import ReadinessWaiter


class ServiceStarter:
    def __init__(self, compose: ComposeRunner, waiter: ReadinessWaiter) -> None:
        self._compose = compose
        self._waiter = waiter

    def start(self, project_root: Path, token: SessionToken, timeout_s: int) -> tuple[ServiceHealth, ...]:
        try:
            self._compose.up(project_root, token, timeout_s)
        except ComposeError as error:
            raise ComposeFailedError(str(error)) from None
        return self._waiter.wait(timeout_s)
