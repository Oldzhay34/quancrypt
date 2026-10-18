"""Coarse-grained entry point of the CLI: init, up, down, status and open."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from quancrypt_cli.facade.errors import CliError
from quancrypt_cli.port.inbound.errors import (
    ComposeFailedError,
    InvalidProjectError,
    NotInitializedError,
    RegistrationFailedError,
    ServicesNotReadyError,
    StateError,
)
from quancrypt_cli.port.inbound.init_project import InitProjectCommand, InitProjectUseCase
from quancrypt_cli.port.inbound.open_browser import OpenBrowserCommand, OpenBrowserUseCase
from quancrypt_cli.port.inbound.report_status import ReportStatusUseCase
from quancrypt_cli.port.inbound.service_status import ServiceStatus
from quancrypt_cli.port.inbound.start_services import StartServicesCommand, StartServicesUseCase
from quancrypt_cli.port.inbound.stop_services import StopServicesUseCase

T = TypeVar("T")


@dataclass(frozen=True)
class ServiceLine:
    name: str
    healthy: bool
    detail: str


@dataclass(frozen=True)
class InitView:
    project_name: str
    kind: str
    newly_registered: bool
    token_renewed: bool
    token_protected: bool
    services: tuple[ServiceLine, ...]
    gitignore_covers: bool
    gitignore_line: str
    ui_address: str


@dataclass(frozen=True)
class StatusView:
    services: tuple[ServiceLine, ...]
    all_required_healthy: bool


@dataclass(frozen=True)
class OpenView:
    address: str


def _lines(services: tuple[ServiceStatus, ...]) -> tuple[ServiceLine, ...]:
    return tuple(ServiceLine(item.name, item.healthy, item.detail) for item in services)


class ProjectFacade:
    """The commands of the CLI. Use-case errors become `CliError`, so the Typer layer knows one error type."""

    def __init__(
        self,
        init: InitProjectUseCase,
        start: StartServicesUseCase,
        stop: StopServicesUseCase,
        status: ReportStatusUseCase,
        open_browser: OpenBrowserUseCase,
    ) -> None:
        self._init = init
        self._start = start
        self._stop = stop
        self._status = status
        self._open = open_browser

    def init(self, path: str, wait_timeout_s: int) -> InitView:
        result = self._guard(lambda: self._init.execute(InitProjectCommand(path, wait_timeout_s)))
        return InitView(
            project_name=result.project_name,
            kind=result.kind,
            newly_registered=result.newly_registered,
            token_renewed=result.token_renewed,
            token_protected=result.token_protected,
            services=_lines(result.services),
            gitignore_covers=result.gitignore_covers,
            gitignore_line=result.gitignore_line,
            ui_address=result.ui_address,
        )

    def up(self, path: str, wait_timeout_s: int) -> tuple[ServiceLine, ...]:
        result = self._guard(lambda: self._start.execute(StartServicesCommand(path, wait_timeout_s)))
        return _lines(result.services)

    def down(self) -> None:
        self._guard(self._stop.execute)

    def status(self) -> StatusView:
        result = self._guard(self._status.execute)
        return StatusView(_lines(result.services), result.all_required_healthy)

    def open_ui(self, path: str) -> OpenView:
        result = self._guard(lambda: self._open.execute(OpenBrowserCommand(path)))
        return OpenView(result.address)

    @staticmethod
    def _guard(action: Callable[[], T]) -> T:
        try:
            return action()
        except InvalidProjectError as error:
            raise CliError(error.reason) from None
        except NotInitializedError:
            raise CliError("not-initialized") from None
        except ComposeFailedError as error:
            raise CliError("compose-failed", str(error)) from None
        except ServicesNotReadyError as error:
            raise CliError("services-not-ready", ", ".join(error.names)) from None
        except RegistrationFailedError as error:
            raise CliError("registration-failed", error.kind) from None
        except StateError as error:
            raise CliError("state-error", str(error)) from None
