"""Outbound port contracts (LSP): the fakes and the real adapters behave the same way."""

from __future__ import annotations

import subprocess
import webbrowser
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from quancrypt_cli.domain.project import ProjectConfig, ProjectKind
from quancrypt_cli.domain.services import AGENT, CORE
from quancrypt_cli.domain.session_token import SessionToken
from quancrypt_cli.infrastructure.docker_compose_runner import DockerComposeRunner
from quancrypt_cli.infrastructure.file_project_state_store import FileProjectStateStore
from quancrypt_cli.infrastructure.http_core_api_client import HttpCoreApiClient
from quancrypt_cli.infrastructure.http_health_probe import HttpHealthProbe
from quancrypt_cli.infrastructure.local_file_system import LocalFileSystem
from quancrypt_cli.infrastructure.secrets_token_generator import SecretsTokenGenerator
from quancrypt_cli.infrastructure.system_clock import SystemClock
from quancrypt_cli.infrastructure.webbrowser_opener import WebbrowserOpener
from quancrypt_cli.port.outbound.browser_opener import BrowserOpener
from quancrypt_cli.port.outbound.clock import Clock
from quancrypt_cli.port.outbound.compose_runner import ComposeRunner
from quancrypt_cli.port.outbound.core_api_client import CoreApiClient
from quancrypt_cli.port.outbound.errors import ComposeError, CoreApiError
from quancrypt_cli.port.outbound.file_system import FileSystem
from quancrypt_cli.port.outbound.health_probe import HealthProbe
from quancrypt_cli.port.outbound.project_state_store import ProjectStateStore
from quancrypt_cli.port.outbound.token_generator import TokenGenerator
from tests.support.fakes import (
    PROJECT_ID,
    CountingTokenGenerator,
    FakeBrowser,
    FakeClock,
    FakeCompose,
    FakeCore,
    FakeFileSystem,
    FakeProbe,
    InMemoryStateStore,
    token,
)

CONFIG = ProjectConfig("qbank", ProjectKind.GRADLE, datetime(2026, 10, 19, 9, 0, tzinfo=UTC), "1.0.0")


# ---- ProjectStateStore ----


@pytest.fixture(params=["in-memory", "files"])
def store(request: pytest.FixtureRequest) -> ProjectStateStore:
    return InMemoryStateStore() if request.param == "in-memory" else FileProjectStateStore()


def test_a_new_project_has_neither_config_nor_token(store: ProjectStateStore, tmp_path: Path) -> None:
    assert store.load_config(tmp_path) is None
    assert store.load_token(tmp_path) is None


def test_a_saved_config_reads_back_equal(store: ProjectStateStore, tmp_path: Path) -> None:
    store.save_config(tmp_path, CONFIG)

    assert store.load_config(tmp_path) == CONFIG


def test_a_saved_token_reads_back_and_a_new_one_replaces_it(store: ProjectStateStore, tmp_path: Path) -> None:
    assert store.save_token(tmp_path, token(1)) is True
    assert store.load_token(tmp_path) == token(1)

    store.save_token(tmp_path, token(2))

    assert store.load_token(tmp_path) == token(2)


def test_projects_do_not_share_state(store: ProjectStateStore, tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    store.save_token(tmp_path / "a", token(1))

    assert store.load_token(tmp_path / "b") is None


# ---- FileSystem ----


def make_fake(root: Path) -> FileSystem:
    return FakeFileSystem({root: frozenset({"pom.xml", "src"})}, {root / ".gitignore": ["target/", ".quancrypt/"]})


def make_local(root: Path) -> FileSystem:
    (root / "src").mkdir(exist_ok=True)
    (root / "pom.xml").write_text("<project/>")
    (root / ".gitignore").write_text("target/\n.quancrypt/\n")
    return LocalFileSystem()


@pytest.fixture(params=[make_fake, make_local], ids=["fake", "local"])
def fs_and_root(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[FileSystem, Path]:
    maker: Callable[[Path], FileSystem] = request.param
    root = tmp_path.resolve()
    return maker(root), root


def test_a_directory_lists_its_names_and_a_missing_one_is_not_a_directory(fs_and_root: tuple[FileSystem, Path]) -> None:
    fs, root = fs_and_root

    assert fs.is_directory(root)
    assert {"pom.xml", "src"} <= fs.entries(root)
    assert not fs.is_directory(root / "nothing")


def test_text_files_read_as_lines_and_a_missing_file_is_none(fs_and_root: tuple[FileSystem, Path]) -> None:
    fs, root = fs_and_root

    assert fs.read_lines(root / ".gitignore") == ["target/", ".quancrypt/"]
    assert fs.read_lines(root / "missing") is None


def test_the_local_file_system_resolves_dots_and_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert LocalFileSystem().absolute(".") == tmp_path.resolve()
    assert LocalFileSystem().absolute("sub/../.") == tmp_path.resolve()
    assert LocalFileSystem().read_lines(tmp_path) is None  # a directory is not a text file


# ---- TokenGenerator ----


@pytest.fixture(params=[CountingTokenGenerator, SecretsTokenGenerator])
def generator(request: pytest.FixtureRequest) -> TokenGenerator:
    return request.param()  # type: ignore[no-any-return]


def test_a_generator_gives_valid_tokens_that_differ(generator: TokenGenerator) -> None:
    first, second = generator.generate(), generator.generate()

    assert isinstance(first, SessionToken) and first != second


# ---- Clock ----


@pytest.fixture(params=["fake", "system"])
def clock(request: pytest.FixtureRequest) -> Clock:
    return FakeClock() if request.param == "fake" else SystemClock()


def test_a_clock_gives_a_timezone_aware_utc_time_and_a_monotonic_reading(clock: Clock) -> None:
    now = clock.now()

    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)
    first = clock.monotonic()
    clock.sleep(0)
    assert clock.monotonic() >= first


# ---- HealthProbe ----


@pytest.fixture(params=["fake", "http"])
def probe(request: pytest.FixtureRequest) -> Iterator[HealthProbe]:
    if request.param == "fake":
        yield FakeProbe(down=["agent-service"])
        return
    with respx.mock:
        respx.get("http://127.0.0.1:8083/health/readiness").mock(side_effect=httpx.ConnectError("refused"))
        respx.get("http://127.0.0.1:8081/health/readiness").mock(return_value=httpx.Response(200))
        yield HttpHealthProbe()


def test_a_probe_answers_with_a_health_value_and_never_raises(probe: HealthProbe) -> None:
    down = probe.check(AGENT)
    up = probe.check(CORE)

    assert (down.name, down.healthy) == ("agent-service", False)
    assert (up.name, up.healthy) == ("core-service", True)


# ---- CoreApiClient ----


@pytest.fixture(params=["fake", "http"])
def core(request: pytest.FixtureRequest) -> Iterator[CoreApiClient]:
    if request.param == "fake":
        yield FakeCore(error=None)
        return
    with respx.mock:
        respx.post("http://127.0.0.1:8081/api/v1/projects").mock(
            return_value=httpx.Response(201, json={"id": PROJECT_ID})
        )
        yield HttpCoreApiClient("http://127.0.0.1:8081")


def test_registering_a_project_returns_its_id_and_whether_it_is_new(core: CoreApiClient) -> None:
    project = core.register_project(token(1), "/work/qbank", "qbank")

    assert project.id == PROJECT_ID and project.created is True


@pytest.mark.parametrize("kind", ["unreachable", "unauthorized", "rejected"])
def test_registration_failures_are_core_api_errors_of_a_known_kind(kind: str) -> None:
    with pytest.raises(CoreApiError) as fake:
        FakeCore(error=CoreApiError(kind)).register_project(token(1), "/w", "w")
    statuses = {"unreachable": None, "unauthorized": 401, "rejected": 500}
    outcome: Exception | httpx.Response = (
        httpx.ConnectError("refused") if statuses[kind] is None else httpx.Response(statuses[kind] or 0)
    )
    with respx.mock:
        respx.post("http://127.0.0.1:8081/api/v1/projects").mock(
            side_effect=[outcome] * 3 if isinstance(outcome, Exception) else None,
            return_value=None if isinstance(outcome, Exception) else outcome,
        )
        with pytest.raises(CoreApiError) as real:
            HttpCoreApiClient("http://127.0.0.1:8081", retry_wait_s=0).register_project(token(1), "/w", "w")

    assert fake.value.kind == real.value.kind == kind


# ---- ComposeRunner ----


def failing_run(args: list[str], **options: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")


@pytest.mark.parametrize("which", ["fake", "docker"])
def test_a_failing_compose_is_a_compose_error_for_up_and_down(which: str, tmp_path: Path) -> None:
    runner: ComposeRunner = (
        FakeCompose(ComposeError("boom")) if which == "fake" else DockerComposeRunner(tmp_path, run=failing_run)
    )

    with pytest.raises(ComposeError):
        runner.up(Path("/work"), token(1), 30)
    with pytest.raises(ComposeError):
        runner.down()


# ---- BrowserOpener ----


@pytest.fixture(params=["fake", "webbrowser"])
def opener(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> BrowserOpener:
    if request.param == "fake":
        return FakeBrowser()
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    return WebbrowserOpener()


def test_an_opener_answers_with_a_bool(opener: BrowserOpener) -> None:
    assert opener.open("http://127.0.0.1:8080/") is True
