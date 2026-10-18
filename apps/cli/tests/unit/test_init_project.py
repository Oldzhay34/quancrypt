"""`quancrypt init`: the transaction plan with fake ports (P5.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from quancrypt_cli.domain.project import ProjectConfig, ProjectKind
from quancrypt_cli.port.inbound.errors import (
    ComposeFailedError,
    InvalidProjectError,
    RegistrationFailedError,
    ServicesNotReadyError,
    StateError,
)
from quancrypt_cli.port.inbound.init_project import InitProjectCommand
from quancrypt_cli.port.outbound.errors import ComposeError, CoreApiError, StateStoreError
from quancrypt_cli.usecase.init_project import InitProject
from quancrypt_cli.usecase.readiness import ReadinessWaiter
from quancrypt_cli.usecase.service_starter import ServiceStarter
from tests.support.fakes import (
    NOW,
    PROJECT_ID,
    ROOT,
    CountingTokenGenerator,
    FakeBrowser,
    FakeClock,
    FakeCompose,
    FakeCore,
    FakeFileSystem,
    FakeProbe,
    InMemoryStateStore,
)

COMMAND = InitProjectCommand(".", 60)


@dataclass
class Rig:
    files: FakeFileSystem = field(default_factory=FakeFileSystem)
    store: InMemoryStateStore = field(default_factory=InMemoryStateStore)
    tokens: CountingTokenGenerator = field(default_factory=CountingTokenGenerator)
    compose: FakeCompose = field(default_factory=FakeCompose)
    probe: FakeProbe = field(default_factory=FakeProbe)
    core: FakeCore = field(default_factory=FakeCore)
    browser: FakeBrowser = field(default_factory=FakeBrowser)
    clock: FakeClock = field(default_factory=FakeClock)

    def use_case(self) -> InitProject:
        starter = ServiceStarter(self.compose, ReadinessWaiter(self.probe, self.clock))
        return InitProject(
            self.files,
            self.store,
            self.tokens,
            starter,
            self.core,
            self.clock,
            "1.0.0",
        )


def test_init_sets_the_project_up_end_to_end() -> None:
    rig = Rig()

    result = rig.use_case().execute(COMMAND)

    assert (result.project_name, result.kind, result.project_id) == ("qbank", "maven", PROJECT_ID)
    assert result.newly_registered and not result.token_renewed and result.token_protected
    assert [s.name for s in result.services] == ["core-service", "analyzer-service", "agent-service"]
    assert all(service.healthy for service in result.services)
    assert rig.store.configs[ROOT] == ProjectConfig("qbank", ProjectKind.MAVEN, NOW, "1.0.0")
    stored = rig.store.tokens[ROOT]
    assert rig.compose.up_calls == [(ROOT, stored, 60)]
    assert rig.core.calls == [(stored, str(ROOT), "qbank")]
    # No browser is started and the answer carries the address without the token (D-279).
    assert rig.browser.urls == []
    assert result.ui_address == "http://127.0.0.1:8080" and stored.value not in repr(result)


def test_a_gradle_root_is_recognised() -> None:
    rig = Rig(files=FakeFileSystem({ROOT: frozenset({"build.gradle.kts"})}))

    assert rig.use_case().execute(COMMAND).kind == "gradle"


@pytest.mark.parametrize(
    ("directories", "reason"),
    [
        ({ROOT: frozenset({"README.md"})}, "no-build-file"),
        ({ROOT: frozenset({"pom.xml", "build.gradle"})}, "ambiguous"),
        ({}, "not-a-directory"),
    ],
)
def test_a_bad_root_stops_before_anything_is_written_or_started(
    directories: dict[Path, frozenset[str]], reason: str
) -> None:
    rig = Rig(files=FakeFileSystem(directories))

    with pytest.raises(InvalidProjectError) as caught:
        rig.use_case().execute(COMMAND)

    assert caught.value.reason == reason
    assert rig.store.writes == [] and rig.compose.up_calls == [] and rig.core.calls == []


def test_a_second_init_makes_a_new_token_keeps_the_config_and_restarts_the_services() -> None:
    rig = Rig()
    first = rig.use_case().execute(COMMAND)
    config = rig.store.configs[ROOT]
    first_token = rig.store.tokens[ROOT]
    rig.core.created = False

    second = rig.use_case().execute(COMMAND)

    assert first.token_renewed is False and second.token_renewed is True
    assert rig.store.tokens[ROOT] != first_token  # D-273
    assert rig.store.configs[ROOT] is config and rig.store.writes.count("config") == 1
    assert [call[1] for call in rig.compose.up_calls] == [first_token, rig.store.tokens[ROOT]]
    assert not second.newly_registered


def test_a_stored_config_keeps_its_name_and_creation_time_even_when_the_folder_changed() -> None:
    rig = Rig()
    rig.store.configs[ROOT] = ProjectConfig("old-name", ProjectKind.GRADLE, NOW, "0.9.0")

    result = rig.use_case().execute(COMMAND)

    assert (result.project_name, result.kind) == ("old-name", "gradle")
    assert rig.core.calls[0][2] == "old-name"


def test_a_failing_compose_stops_before_registration_and_the_browser() -> None:
    rig = Rig(compose=FakeCompose(ComposeError("docker compose up exited with code 1: boom")))

    with pytest.raises(ComposeFailedError, match="exited with code 1"):
        rig.use_case().execute(COMMAND)

    assert rig.core.calls == [] and rig.browser.urls == []


def test_services_that_never_answer_are_reported_by_name() -> None:
    rig = Rig(probe=FakeProbe(down=["analyzer-service"]))

    with pytest.raises(ServicesNotReadyError) as caught:
        rig.use_case().execute(InitProjectCommand(".", 10))

    assert caught.value.names == ("analyzer-service",)
    assert rig.core.calls == [] and rig.browser.urls == []
    assert rig.clock.time >= 10  # it waited for the whole timeout


@pytest.mark.parametrize("kind", ["unreachable", "unauthorized", "rejected"])
def test_a_registration_failure_keeps_its_kind_and_opens_no_browser(kind: str) -> None:
    rig = Rig(core=FakeCore(error=CoreApiError(kind)))

    with pytest.raises(RegistrationFailedError) as caught:
        rig.use_case().execute(COMMAND)

    assert caught.value.kind == kind
    assert rig.browser.urls == []


def test_an_answering_port_8080_is_never_trusted_and_never_probed() -> None:
    rig = Rig()

    rig.use_case().execute(COMMAND)

    assert "web-ui" not in rig.probe.calls  # a squatter on 8080 would otherwise receive the token (D-279)


def test_the_gitignore_is_only_read_never_written() -> None:
    rig = Rig()
    assert rig.use_case().execute(COMMAND).gitignore_covers is False  # no .gitignore: advise (D-272)

    rig.files.files[ROOT / ".gitignore"] = ["target/", ".quancrypt/"]
    assert rig.use_case().execute(COMMAND).gitignore_covers is True
    assert rig.store.writes.count("config") == 1  # the store writes `.quancrypt/` only; there is no other writer port


def test_a_file_system_that_ignores_permissions_is_reported() -> None:
    rig = Rig(store=InMemoryStateStore(protected=False))

    assert rig.use_case().execute(COMMAND).token_protected is False


def test_a_state_store_failure_is_a_state_error_and_nothing_starts() -> None:
    rig = Rig()
    rig.store.fail_with = StateStoreError("config.yaml is unreadable or malformed")

    with pytest.raises(StateError, match="unreadable"):
        rig.use_case().execute(COMMAND)

    assert rig.compose.up_calls == []
