"""The facade (error translation) and the Typer commands (output, exit codes, languages)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from quancrypt_cli.api.commands import build_app
from quancrypt_cli.api.messages import language_from, text
from quancrypt_cli.facade.errors import CliError
from quancrypt_cli.facade.project_facade import InitView, ProjectFacade, ServiceLine, StatusView
from quancrypt_cli.port.inbound.errors import (
    ComposeFailedError,
    InvalidProjectError,
    NotInitializedError,
    RegistrationFailedError,
    ServicesNotReadyError,
    StateError,
)
from quancrypt_cli.port.inbound.init_project import InitProjectResult
from quancrypt_cli.port.inbound.open_browser import OpenBrowserResult
from quancrypt_cli.port.inbound.report_status import StatusResult
from quancrypt_cli.port.inbound.service_status import ServiceStatus

SERVICES = (ServiceStatus("core-service", True, "HTTP 200"), ServiceStatus("agent-service", False, "not reachable"))
RESULT = InitProjectResult(
    "qbank", "maven", "id", True, False, True, SERVICES, False, ".quancrypt/", "http://127.0.0.1:8080"
)


class ScriptedUseCases:
    """One object plays all five inbound ports; `error` is raised by every call."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def _maybe(self) -> None:
        if self.error:
            raise self.error

    def execute(self, *arguments: object) -> object:
        self._maybe()
        if not arguments:
            return StatusResult(SERVICES, False)
        return RESULT


def facade(error: Exception | None = None) -> ProjectFacade:
    cases = ScriptedUseCases(error)
    return ProjectFacade(cases, cases, cases, cases, cases)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        (InvalidProjectError("no-build-file"), "no-build-file", ""),
        (InvalidProjectError("ambiguous"), "ambiguous", ""),
        (NotInitializedError(), "not-initialized", ""),
        (
            ComposeFailedError("docker compose up exited with code 1"),
            "compose-failed",
            "docker compose up exited with code 1",
        ),
        (ServicesNotReadyError(("core-service", "agent-service")), "services-not-ready", "core-service, agent-service"),
        (RegistrationFailedError("unauthorized"), "registration-failed", "unauthorized"),
        (StateError("config.yaml is unreadable"), "state-error", "config.yaml is unreadable"),
    ],
)
def test_the_facade_turns_every_use_case_error_into_one_cli_error(error: Exception, code: str, detail: str) -> None:
    with pytest.raises(CliError) as caught:
        facade(error).init(".", 30)

    assert (caught.value.code, caught.value.detail) == (code, detail)


def test_the_facade_maps_results_to_views() -> None:
    view = facade().init(".", 30)

    assert isinstance(view, InitView) and view.project_name == "qbank"
    assert view.services == (
        ServiceLine("core-service", True, "HTTP 200"),
        ServiceLine("agent-service", False, "not reachable"),
    )
    assert isinstance(facade().status(), StatusView)


class ViewFacade:
    """A facade double for the Typer layer: it returns fixed views or raises."""

    def __init__(self, init: InitView | None = None, error: CliError | None = None, all_ok: bool = True) -> None:
        self._init = init
        self._error = error
        self._all_ok = all_ok

    def _guard(self) -> None:
        if self._error:
            raise self._error

    def init(self, path: str, wait_timeout_s: int) -> InitView:
        self._guard()
        assert self._init is not None
        return self._init

    def up(self, path: str, wait_timeout_s: int) -> tuple[ServiceLine, ...]:
        self._guard()
        return (ServiceLine("core-service", True, ""),)

    def down(self) -> None:
        self._guard()

    def status(self) -> StatusView:
        self._guard()
        return StatusView(
            (ServiceLine("core-service", self._all_ok, ""), ServiceLine("web-ui", False, "")), self._all_ok
        )

    def open_ui(self, path: str) -> object:
        self._guard()
        return OpenBrowserResult("http://127.0.0.1:8080")


def view(**changes: object) -> InitView:
    values: dict[str, object] = {
        "project_name": "qbank",
        "kind": "maven",
        "newly_registered": True,
        "token_renewed": False,
        "token_protected": True,
        "services": (ServiceLine("core-service", True, ""),),
        "gitignore_covers": True,
        "gitignore_line": ".quancrypt/",
        "ui_address": "http://127.0.0.1:8080",
    }
    values.update(changes)
    return InitView(**values)  # type: ignore[arg-type]


def run(fake: ViewFacade, *arguments: str, language: str = "en"):  # type: ignore[no-untyped-def]
    app = build_app(lambda: fake, language)  # type: ignore[arg-type,return-value]
    return CliRunner().invoke(app, list(arguments))


def test_init_prints_the_outcome_the_services_and_the_privacy_note() -> None:
    result = run(ViewFacade(init=view()), "init")

    assert result.exit_code == 0
    assert "Starting the services" in result.stdout
    assert "Quancrypt is ready: qbank (maven)" in result.stdout
    assert "core-service" in result.stdout and "registered in core-service" in result.stdout
    assert "Web UI address: http://127.0.0.1:8080" in result.stdout and "#token" not in result.stdout
    assert "Privacy note" in result.stdout


def test_init_warns_about_a_missing_gitignore_line_a_renewed_token_and_unprotected_permissions() -> None:
    result = run(ViewFacade(init=view(gitignore_covers=False, token_renewed=True, token_protected=False)), "init")

    assert "Add this line yourself: .quancrypt/" in result.stdout
    assert "new session token" in result.stdout
    assert "does not support file permissions" in result.stdout


def test_the_turkish_texts_are_the_default() -> None:
    app = build_app(lambda: ViewFacade(init=view()), language_from(None))  # type: ignore[arg-type,return-value]

    result = CliRunner().invoke(app, ["init"])

    assert "Quancrypt hazır: qbank (maven)" in result.stdout and "KVKK notu" in result.stdout


def test_an_error_goes_to_stderr_with_exit_code_one_and_no_traceback() -> None:
    result = run(ViewFacade(error=CliError("no-build-file")), "init", language="en")

    assert result.exit_code == 1
    assert "Error: This directory is not a Maven or Gradle project root" in result.stderr
    assert "Traceback" not in result.output


def test_error_detail_is_shown_and_every_code_has_both_languages() -> None:
    result = run(ViewFacade(error=CliError("services-not-ready", "core-service")), "up")
    assert "core-service" in result.stderr and result.exit_code == 1
    for code in (
        "not-a-directory",
        "no-build-file",
        "ambiguous",
        "not-initialized",
        "compose-failed",
        "services-not-ready",
        "registration-failed",
        "state-error",
        "install-not-found",
        "unexpected",
    ):
        assert text("tr", code, detail="x") and text("en", code, detail="x")


def test_status_exits_one_when_a_required_service_is_down() -> None:
    assert run(ViewFacade(all_ok=True), "status").exit_code == 0
    bad = run(ViewFacade(all_ok=False), "status")
    assert bad.exit_code == 1 and "not ready" in bad.stdout


def test_up_down_and_open_work() -> None:
    assert "The services are running." in run(ViewFacade(), "up").stdout
    assert "stopped" in run(ViewFacade(), "down").stdout
    assert "Web UI address: http://127.0.0.1:8080" in run(ViewFacade(), "open").stdout


def test_help_needs_no_installation_and_lists_the_commands() -> None:
    def never() -> ProjectFacade:
        raise AssertionError("the facade must not be built for --help")

    result = CliRunner().invoke(build_app(never, "en"), ["--help"])

    assert result.exit_code == 0
    for command in ("init", "up", "down", "status", "open"):
        assert command in result.stdout


def test_an_unknown_language_falls_back_to_turkish() -> None:
    assert language_from("de") == "tr" and language_from("en") == "en"
