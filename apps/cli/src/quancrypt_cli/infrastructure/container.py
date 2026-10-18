"""Composition root: the only place that creates and wires the concrete classes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from quancrypt_cli import __version__
from quancrypt_cli.domain.services import CORE_BASE_URL
from quancrypt_cli.facade.errors import CliError
from quancrypt_cli.facade.project_facade import ProjectFacade
from quancrypt_cli.infrastructure.docker_compose_runner import DockerComposeRunner
from quancrypt_cli.infrastructure.file_project_state_store import FileProjectStateStore
from quancrypt_cli.infrastructure.http_core_api_client import HttpCoreApiClient
from quancrypt_cli.infrastructure.http_health_probe import HttpHealthProbe
from quancrypt_cli.infrastructure.local_file_system import LocalFileSystem
from quancrypt_cli.infrastructure.secrets_token_generator import SecretsTokenGenerator
from quancrypt_cli.infrastructure.settings import InstallNotFoundError, load_settings
from quancrypt_cli.infrastructure.system_clock import SystemClock
from quancrypt_cli.usecase.init_project import InitProject
from quancrypt_cli.usecase.open_browser import OpenBrowser
from quancrypt_cli.usecase.readiness import ReadinessWaiter
from quancrypt_cli.usecase.report_status import ReportStatus
from quancrypt_cli.usecase.service_starter import ServiceStarter
from quancrypt_cli.usecase.start_services import StartServices
from quancrypt_cli.usecase.stop_services import StopServices


def build_facade(env: Mapping[str, str], user_home: Path | None = None) -> ProjectFacade:
    """Wire the CLI for the Quancrypt installation the environment points to."""
    try:
        settings = load_settings(env, user_home or Path.home())
    except InstallNotFoundError as error:
        raise CliError("install-not-found", str(error)) from None
    files = LocalFileSystem()
    store = FileProjectStateStore()
    clock = SystemClock()
    probe = HttpHealthProbe()
    compose = DockerComposeRunner(settings.home)
    starter = ServiceStarter(compose, ReadinessWaiter(probe, clock))
    return ProjectFacade(
        init=InitProject(
            files,
            store,
            SecretsTokenGenerator(),
            starter,
            HttpCoreApiClient(CORE_BASE_URL),
            clock,
            __version__,
        ),
        start=StartServices(files, store, starter),
        stop=StopServices(compose),
        status=ReportStatus(probe),
        open_browser=OpenBrowser(files, store),
    )
