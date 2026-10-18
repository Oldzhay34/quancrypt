"""Use case: `quancrypt down` stops the services; the database volume stays."""

from __future__ import annotations

from quancrypt_cli.port.inbound.errors import ComposeFailedError
from quancrypt_cli.port.outbound.compose_runner import ComposeRunner
from quancrypt_cli.port.outbound.errors import ComposeError


class StopServices:
    """Implements StopServicesUseCase."""

    def __init__(self, compose: ComposeRunner) -> None:
        self._compose = compose

    def execute(self) -> None:
        try:
            self._compose.down()
        except ComposeError as error:
            raise ComposeFailedError(str(error)) from None
