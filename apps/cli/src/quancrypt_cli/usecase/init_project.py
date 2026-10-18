"""Use case: `quancrypt init` (FR-01, FR-02): recognise the project, write `.quancrypt/`, start the services, register
the project in core-service and open the web UI. Only `.quancrypt/` is written in the user's project (D-272)."""

from __future__ import annotations

from quancrypt_cli.domain.errors import AmbiguousProjectError, NotAProjectError
from quancrypt_cli.domain.gitignore import IGNORE_LINE, covers_quancrypt
from quancrypt_cli.domain.project import ProjectConfig, detect_kind, display_name
from quancrypt_cli.domain.services import UI_URL
from quancrypt_cli.port.inbound.errors import InvalidProjectError, RegistrationFailedError, StateError
from quancrypt_cli.port.inbound.init_project import InitProjectCommand, InitProjectResult
from quancrypt_cli.port.inbound.service_status import ServiceStatus
from quancrypt_cli.port.outbound.clock import Clock
from quancrypt_cli.port.outbound.core_api_client import CoreApiClient
from quancrypt_cli.port.outbound.errors import CoreApiError, StateStoreError
from quancrypt_cli.port.outbound.file_system import FileSystem
from quancrypt_cli.port.outbound.project_state_store import ProjectStateStore
from quancrypt_cli.port.outbound.token_generator import TokenGenerator
from quancrypt_cli.usecase.service_starter import ServiceStarter


class InitProject:
    """Implements InitProjectUseCase. Eight collaborators: each is a narrow port or one step of the transaction plan
    (init is the one command that touches every outbound port, D-277)."""

    def __init__(
        self,
        files: FileSystem,
        store: ProjectStateStore,
        tokens: TokenGenerator,
        starter: ServiceStarter,
        core: CoreApiClient,
        clock: Clock,
        quancrypt_version: str,
    ) -> None:
        self._files = files
        self._store = store
        self._tokens = tokens
        self._starter = starter
        self._core = core
        self._clock = clock
        self._version = quancrypt_version

    def execute(self, command: InitProjectCommand) -> InitProjectResult:
        root = self._files.absolute(command.path)
        # Nothing is written before the directory is known to be a Maven or Gradle project root.
        if not self._files.is_directory(root):
            raise InvalidProjectError("not-a-directory")
        try:
            kind = detect_kind(self._files.entries(root))
        except OSError:
            raise InvalidProjectError("unreadable") from None
        except NotAProjectError:
            raise InvalidProjectError("no-build-file") from None
        except AmbiguousProjectError:
            raise InvalidProjectError("ambiguous") from None

        try:
            existing = self._store.load_config(root)
            config = existing or ProjectConfig(display_name(root.name), kind, self._clock.now(), self._version)
            if existing is None:
                self._store.save_config(root, config)
            token_renewed = self._store.load_token(root) is not None
            token = self._tokens.generate()  # a new token on every init (D-273)
            protected = self._store.save_token(root, token)
        except StateStoreError as error:
            raise StateError(str(error)) from None

        health = self._starter.start(root, token, command.wait_timeout_s)
        try:
            project = self._core.register_project(token, str(root), config.name)
        except CoreApiError as error:
            raise RegistrationFailedError(error.kind) from None
        lines = self._files.read_lines(root / ".gitignore") or []
        return InitProjectResult(
            project_name=config.name,
            kind=config.kind.value,
            project_id=project.id,
            newly_registered=project.created,
            token_renewed=token_renewed,
            token_protected=protected,
            services=tuple(ServiceStatus(item.name, item.healthy, item.detail) for item in health),
            gitignore_covers=covers_quancrypt(lines),
            gitignore_line=IGNORE_LINE,
            ui_address=UI_URL,
        )
