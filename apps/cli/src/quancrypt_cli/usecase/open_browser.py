"""Use case: `quancrypt open` shows where the web UI is (D-279: no browser is started before the web UI exists)."""

from __future__ import annotations

from quancrypt_cli.domain.services import UI_URL
from quancrypt_cli.port.inbound.errors import InvalidProjectError, NotInitializedError, StateError
from quancrypt_cli.port.inbound.open_browser import OpenBrowserCommand, OpenBrowserResult
from quancrypt_cli.port.outbound.errors import StateStoreError
from quancrypt_cli.port.outbound.file_system import FileSystem
from quancrypt_cli.port.outbound.project_state_store import ProjectStateStore


class OpenBrowser:
    """Implements OpenBrowserUseCase."""

    def __init__(self, files: FileSystem, store: ProjectStateStore) -> None:
        self._files = files
        self._store = store

    def execute(self, command: OpenBrowserCommand) -> OpenBrowserResult:
        root = self._files.absolute(command.path)
        if not self._files.is_directory(root):
            raise InvalidProjectError("not-a-directory")
        try:
            known = self._store.load_token(root) is not None
        except StateStoreError as error:
            raise StateError(str(error)) from None
        if not known:
            raise NotInitializedError
        return OpenBrowserResult(UI_URL)
