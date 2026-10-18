"""The adapters: token file permissions, compose arguments, HTTP probes and client, settings."""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from quancrypt_cli.domain.project import ProjectConfig, ProjectKind
from quancrypt_cli.domain.services import AGENT, WEB_UI
from quancrypt_cli.infrastructure.docker_compose_runner import DockerComposeRunner
from quancrypt_cli.infrastructure.file_project_state_store import FileProjectStateStore
from quancrypt_cli.infrastructure.http_core_api_client import HttpCoreApiClient
from quancrypt_cli.infrastructure.http_health_probe import HttpHealthProbe
from quancrypt_cli.infrastructure.secrets_token_generator import SecretsTokenGenerator
from quancrypt_cli.infrastructure.settings import InstallNotFoundError, load_settings
from quancrypt_cli.infrastructure.webbrowser_opener import WebbrowserOpener
from quancrypt_cli.port.outbound.errors import ComposeError, CoreApiError, StateStoreError
from tests.support.fakes import PROJECT_ID, token

CONFIG = ProjectConfig("qbank", ProjectKind.MAVEN, datetime(2026, 10, 19, 9, 0, tzinfo=UTC), "1.0.0")


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ---- token generator ----


def test_generated_tokens_are_valid_and_different() -> None:
    generator = SecretsTokenGenerator()

    tokens = {generator.generate().value for _ in range(50)}

    assert len(tokens) == 50 and all(len(value) == 43 for value in tokens)


# ---- the state directory ----


def test_the_token_file_is_mode_600_even_under_a_permissive_umask(tmp_path: Path) -> None:
    store = FileProjectStateStore()
    previous = os.umask(0o000)
    try:
        protected = store.save_token(tmp_path, token(1))
    finally:
        os.umask(previous)

    assert protected is True
    assert mode(tmp_path / ".quancrypt" / "session.token") == 0o600
    assert mode(tmp_path / ".quancrypt") == 0o700


def test_an_old_token_file_with_wide_permissions_is_replaced_not_reused(tmp_path: Path) -> None:
    store = FileProjectStateStore()
    directory = tmp_path / ".quancrypt"
    directory.mkdir()
    old = directory / "session.token"
    old.write_text("old-token")
    old.chmod(0o666)

    assert store.save_token(tmp_path, token(2)) is True

    assert mode(old) == 0o600 and old.read_text().strip() == token(2).value
    assert sorted(entry.name for entry in directory.iterdir()) == ["session.token"]  # no temporary file is left


def test_a_token_written_by_init_reads_back(tmp_path: Path) -> None:
    store = FileProjectStateStore()
    store.save_token(tmp_path, token(4))

    assert store.load_token(tmp_path) == token(4)
    assert FileProjectStateStore().load_token(tmp_path / "other") is None


def test_the_config_has_the_four_documented_keys(tmp_path: Path) -> None:
    store = FileProjectStateStore()
    store.save_config(tmp_path, CONFIG)

    text = (tmp_path / ".quancrypt" / "config.yaml").read_text()

    assert [line.split(":")[0] for line in text.splitlines()] == ["name", "kind", "created_at", "quancrypt_version"]
    assert store.load_config(tmp_path) == CONFIG


def test_a_config_behind_a_symbolic_link_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "config.yaml").write_text("name: x")
    project = tmp_path / "project"
    project.mkdir()
    (project / ".quancrypt").symlink_to(real)

    with pytest.raises(StateStoreError, match="symbolic link"):
        FileProjectStateStore().load_config(project)


def test_a_malformed_config_or_token_is_a_store_error_without_the_content(tmp_path: Path) -> None:
    directory = tmp_path / ".quancrypt"
    directory.mkdir()
    (directory / "config.yaml").write_text("name: [unclosed")
    (directory / "session.token").write_text("not-a-token-SECRET")
    store = FileProjectStateStore()

    with pytest.raises(StateStoreError) as config_error:
        store.load_config(tmp_path)
    with pytest.raises(StateStoreError) as token_error:
        store.load_token(tmp_path)

    assert "SECRET" not in str(config_error.value) and "SECRET" not in str(token_error.value)


def test_a_symbolic_link_for_the_state_directory_or_the_token_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".quancrypt").symlink_to(outside)

    with pytest.raises(StateStoreError):
        FileProjectStateStore().save_token(project, token(1))
    assert list(outside.iterdir()) == []  # nothing was written through the link

    other = tmp_path / "other"
    (other / ".quancrypt").mkdir(parents=True)
    target = tmp_path / "target.txt"
    target.write_text("keep")
    (other / ".quancrypt" / "session.token").symlink_to(target)
    with pytest.raises(StateStoreError):
        FileProjectStateStore().save_token(other, token(1))
    assert target.read_text() == "keep"


# ---- docker compose ----


class RecordingRun:
    def __init__(self, returncode: int = 0, stderr: str = "", raises: BaseException | None = None) -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.raises = raises
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, args: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(args), options))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(args, self.returncode, stdout="", stderr=self.stderr)


def test_up_runs_a_fixed_argument_list_with_the_token_only_in_the_environment(tmp_path: Path) -> None:
    run = RecordingRun()
    secret = token(9)

    DockerComposeRunner(tmp_path, run=run).up(Path("/work/qbank"), secret, 90)

    arguments, options = run.calls[0]
    assert arguments == [
        "docker",
        "compose",
        "--project-directory",
        str(tmp_path),
        "--env-file",
        str(tmp_path / ".env"),
        "-f",
        str(tmp_path / "docker-compose.yml"),
        "--profile",
        "app",
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "90",
    ]
    assert not any(secret.value in argument for argument in arguments)
    assert options["env"]["QUANCRYPT_SESSION_TOKEN"] == secret.value and options["env"]["PROJECT_ROOT"] == "/work/qbank"
    assert not options.get("shell") and options["check"] is False and options["timeout"] > 90


def test_down_uses_the_same_profile_and_no_token(tmp_path: Path) -> None:
    run = RecordingRun()

    DockerComposeRunner(tmp_path, run=run).down()

    assert run.calls[0][0][-3:] == ["--profile", "app", "down"]


def test_a_compose_failure_keeps_the_exit_code_and_the_last_lines_with_the_token_blanked(tmp_path: Path) -> None:
    secret = token(6)
    stderr = "\n".join(f"line {number}" for number in range(20)) + f"\nbad token {secret.value}"
    runner = DockerComposeRunner(tmp_path, run=RecordingRun(returncode=1, stderr=stderr))

    with pytest.raises(ComposeError) as caught:
        runner.up(Path("/work"), secret, 30)

    message = str(caught.value)
    assert "code 1" in message and "line 19" in message and "line 0" not in message
    assert secret.value not in message and "***" in message


@pytest.mark.parametrize(
    ("raises", "expected"),
    [
        (FileNotFoundError(), "docker command was not found"),
        (subprocess.TimeoutExpired("docker", 5), "did not finish"),
        (PermissionError(), "could not be started"),
    ],
)
def test_a_missing_docker_a_timeout_or_an_os_error_is_a_compose_error(
    tmp_path: Path, raises: BaseException, expected: str
) -> None:
    runner = DockerComposeRunner(tmp_path, run=RecordingRun(raises=raises))

    with pytest.raises(ComposeError, match=expected):
        runner.up(Path("/work"), token(1), 30)


def test_the_token_is_in_no_log_record(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    secret = token(8)

    DockerComposeRunner(tmp_path, run=RecordingRun()).up(Path("/work"), secret, 30)

    assert secret.value not in caplog.text and secret.value not in " ".join(r.getMessage() for r in caplog.records)


# ---- HTTP ----


@respx.mock
def test_the_probe_judges_readiness_strictly_and_the_ui_loosely() -> None:
    respx.get("http://127.0.0.1:8083/health/readiness").mock(return_value=httpx.Response(200))
    respx.get("http://127.0.0.1:8080/").mock(return_value=httpx.Response(404))
    probe = HttpHealthProbe()

    assert probe.check(AGENT).healthy
    assert probe.check(WEB_UI).healthy  # any answer below 500 means something serves on the address


@respx.mock
def test_the_probe_reports_a_5xx_a_non_200_readiness_and_a_connection_error_as_unhealthy() -> None:
    respx.get("http://127.0.0.1:8083/health/readiness").mock(return_value=httpx.Response(503))
    respx.get("http://127.0.0.1:8080/").mock(side_effect=httpx.ConnectError("refused"))
    probe = HttpHealthProbe()

    assert not probe.check(AGENT).healthy and probe.check(AGENT).detail == "HTTP 503"
    assert (probe.check(WEB_UI).healthy, probe.check(WEB_UI).detail) == (False, "not reachable")


@respx.mock
def test_the_probe_never_calls_a_non_local_address() -> None:
    route = respx.get("http://example.com/").mock(return_value=httpx.Response(200))
    from quancrypt_cli.domain.services import ServiceEndpoint

    health = HttpHealthProbe().check(ServiceEndpoint("x", "http://example.com/", True, True))

    assert not health.healthy and not route.called


BASE = "http://127.0.0.1:8081"


@respx.mock
def test_registration_sends_the_bearer_token_an_idempotency_key_and_the_identity() -> None:
    route = respx.post(f"{BASE}/api/v1/projects").mock(
        return_value=httpx.Response(201, json={"id": PROJECT_ID, "projectKey": "a" * 64})
    )
    secret = token(3)

    project = HttpCoreApiClient(BASE).register_project(secret, "/work/qbank", "qbank")

    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {secret.value}"
    assert request.headers["Idempotency-Key"] and request.headers["X-Trace-Id"]
    assert request.content == b'{"identity":"/work/qbank","displayName":"qbank"}'
    assert project.id == PROJECT_ID and project.created


@respx.mock
def test_an_already_known_project_is_not_created_again() -> None:
    respx.post(f"{BASE}/api/v1/projects").mock(return_value=httpx.Response(200, json={"id": PROJECT_ID}))

    assert HttpCoreApiClient(BASE).register_project(token(1), "/w", "w").created is False


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "unauthorized"), (403, "unauthorized"), (400, "rejected"), (409, "rejected"), (500, "rejected")],
)
def test_error_statuses_become_core_api_errors_without_the_body(status: int, kind: str) -> None:
    respx.post(f"{BASE}/api/v1/projects").mock(return_value=httpx.Response(status, text="SECRET BODY"))

    with pytest.raises(CoreApiError) as caught:
        HttpCoreApiClient(BASE).register_project(token(1), "/w", "w")

    assert caught.value.kind == kind and "SECRET" not in str(caught.value)


@respx.mock
def test_a_connection_failure_is_retried_three_times_then_unreachable() -> None:
    route = respx.post(f"{BASE}/api/v1/projects").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(CoreApiError) as caught:
        HttpCoreApiClient(BASE, retry_wait_s=0).register_project(token(1), "/w", "w")

    assert caught.value.kind == "unreachable" and route.call_count == 3


@respx.mock
def test_a_connection_that_recovers_registers_the_project() -> None:
    respx.post(f"{BASE}/api/v1/projects").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(201, json={"id": PROJECT_ID})]
    )

    assert HttpCoreApiClient(BASE, retry_wait_s=0).register_project(token(1), "/w", "w").created


@respx.mock
@pytest.mark.parametrize("payload", [{"id": "not-a-uuid"}, {}, ["x"]])
def test_an_answer_without_a_valid_project_id_is_rejected(payload: object) -> None:
    respx.post(f"{BASE}/api/v1/projects").mock(return_value=httpx.Response(201, json=payload))

    with pytest.raises(CoreApiError) as caught:
        HttpCoreApiClient(BASE).register_project(token(1), "/w", "w")

    assert caught.value.kind == "rejected"


def test_the_core_client_refuses_a_non_local_address() -> None:
    with pytest.raises(ValueError, match="local"):
        HttpCoreApiClient("http://example.com")


# ---- settings, browser ----


def home(tmp_path: Path) -> Path:
    directory = tmp_path / "install"
    directory.mkdir()
    (directory / "docker-compose.yml").write_text("name: quancrypt\n")
    (directory / ".env").write_text("X=1\n")
    return directory


def test_the_home_comes_from_the_environment(tmp_path: Path) -> None:
    installed = home(tmp_path)

    assert load_settings({"QUANCRYPT_HOME": str(installed)}, tmp_path / "user").home == installed.resolve()


def test_the_home_comes_from_the_user_config_when_the_variable_is_missing(tmp_path: Path) -> None:
    installed = home(tmp_path)
    config = tmp_path / "user" / ".config" / "quancrypt" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(f"home: {installed}\n")

    assert load_settings({}, tmp_path / "user").home == installed.resolve()


def test_the_variable_wins_over_the_config_file(tmp_path: Path) -> None:
    installed = home(tmp_path)
    config = tmp_path / "user" / ".config" / "quancrypt" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("home: /does/not/exist\n")

    assert load_settings({"QUANCRYPT_HOME": str(installed)}, tmp_path / "user").home == installed.resolve()


@pytest.mark.parametrize("config_text", [None, "home: [1]\n", "- a\n- b\n", "home: [unclosed"])
def test_no_usable_home_is_an_install_error_that_names_the_way_out(tmp_path: Path, config_text: str | None) -> None:
    if config_text is not None:
        config = tmp_path / "user" / ".config" / "quancrypt" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(config_text)

    with pytest.raises(InstallNotFoundError, match="QUANCRYPT_HOME"):
        load_settings({}, tmp_path / "user")


def test_a_relative_home_or_a_home_without_compose_file_or_env_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InstallNotFoundError, match="absolute"):
        load_settings({"QUANCRYPT_HOME": "relative/dir"}, tmp_path)
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(InstallNotFoundError, match="docker-compose.yml"):
        load_settings({"QUANCRYPT_HOME": str(bare)}, tmp_path)
    (bare / "docker-compose.yml").write_text("x")
    with pytest.raises(InstallNotFoundError, match=r"\.env"):
        load_settings({"QUANCRYPT_HOME": str(bare)}, tmp_path)


def test_the_browser_adapter_reports_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webbrowser, "open", lambda url: url.startswith("http://127.0.0.1"))
    assert WebbrowserOpener().open("http://127.0.0.1:8080/#token=x") is True

    def broken(url: str) -> bool:
        raise webbrowser.Error("no browser")

    monkeypatch.setattr(webbrowser, "open", broken)
    assert WebbrowserOpener().open("http://127.0.0.1:8080/") is False
