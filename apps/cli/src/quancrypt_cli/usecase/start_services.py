"""Use case: `quancrypt up` starts the services of an initialised project with its stored token."""

from __future__ import annotations

from quancrypt_cli.port.inbound.errors import InvalidProjectError, NotInitializedError, StateError
from quancrypt_cli.port.inbound.service_status import ServiceStatus
from quancrypt_cli.port.inbound.start_services import StartServicesCommand, StartServicesResult
from quancrypt_cli.port.outbound.errors import StateStoreError
from quancrypt_cli.port.outbound.file_system import FileSystem
from quancrypt_cli.port.outbound.project_state_store import ProjectStateStore
from quancrypt_cli.usecase.service_starter import ServiceStarter


class StartServices:
    """Implements StartServicesUseCase."""

    def __init__(self, files: FileSystem, store: ProjectStateStore, starter: ServiceStarter) -> None:
        self._files = files
        self._store = store
        self._starter = starter

    def execute(self, command: StartServicesCommand) -> StartServicesResult:
        root = self._files.absolute(command.path)
        if not self._files.is_directory(root):
            raise InvalidProjectError("not-a-directory")
        try:
            config = self._store.load_config(root)
            token = self._store.load_token(root)
        except StateStoreError as error:
            raise StateError(str(error)) from None
        if config is None or token is None:
            raise NotInitializedError
        health = self._starter.start(root, token, command.wait_timeout_s)
        return StartServicesResult(tuple(ServiceStatus(item.name, item.healthy, item.detail) for item in health))
