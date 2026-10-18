"""`up`, `down`, `status`, `open` and the readiness wait."""

from __future__ import annotations

import pytest

from quancrypt_cli.domain.project import ProjectConfig, ProjectKind
from quancrypt_cli.port.inbound.errors import (
    ComposeFailedError,
    InvalidProjectError,
    NotInitializedError,
    ServicesNotReadyError,
)
from quancrypt_cli.port.inbound.open_browser import OpenBrowserCommand
from quancrypt_cli.port.inbound.start_services import StartServicesCommand
from quancrypt_cli.port.outbound.errors import ComposeError
from quancrypt_cli.usecase.open_browser import OpenBrowser
from quancrypt_cli.usecase.readiness import ReadinessWaiter
from quancrypt_cli.usecase.report_status import ReportStatus
from quancrypt_cli.usecase.service_starter import ServiceStarter
from quancrypt_cli.usecase.start_services import StartServices
from quancrypt_cli.usecase.stop_services import StopServices
from tests.support.fakes import (
    NOW,
    ROOT,
    FakeClock,
    FakeCompose,
    FakeFileSystem,
    FakeProbe,
    InMemoryStateStore,
    token,
)


def initialised() -> InMemoryStateStore:
    store = InMemoryStateStore()
    store.configs[ROOT] = ProjectConfig("qbank", ProjectKind.MAVEN, NOW, "1.0.0")
    store.tokens[ROOT] = token(5)
    return store


def test_the_waiter_polls_until_every_backend_service_answers() -> None:
    clock = FakeClock()
    waiter = ReadinessWaiter(FakeProbe(ready_after=2), clock, interval_s=2.0)

    health = waiter.wait(60)

    assert all(item.healthy for item in health)
    assert clock.sleeps == [2.0, 2.0]


def test_the_waiter_tries_once_even_with_no_time_and_names_what_is_down() -> None:
    probe = FakeProbe(down=["core-service", "agent-service"])

    with pytest.raises(ServicesNotReadyError) as caught:
        ReadinessWaiter(probe, FakeClock()).wait(0)

    assert caught.value.names == ("core-service", "agent-service")
    assert probe.calls.count("core-service") == 1


def test_up_starts_the_services_with_the_stored_token() -> None:
    compose = FakeCompose()
    starter = ServiceStarter(compose, ReadinessWaiter(FakeProbe(), FakeClock()))
    use_case = StartServices(FakeFileSystem(), initialised(), starter)

    result = use_case.execute(StartServicesCommand(".", 30))

    assert compose.up_calls == [(ROOT, token(5), 30)]
    assert [s.healthy for s in result.services] == [True, True, True]


@pytest.mark.parametrize("missing", ["config", "token"])
def test_up_needs_an_initialised_project(missing: str) -> None:
    store = initialised()
    (store.configs if missing == "config" else store.tokens).clear()
    compose = FakeCompose()
    use_case = StartServices(
        FakeFileSystem(), store, ServiceStarter(compose, ReadinessWaiter(FakeProbe(), FakeClock()))
    )

    with pytest.raises(NotInitializedError):
        use_case.execute(StartServicesCommand(".", 30))

    assert compose.up_calls == []


def test_up_refuses_a_path_that_is_not_a_directory() -> None:
    starter = ServiceStarter(FakeCompose(), ReadinessWaiter(FakeProbe(), FakeClock()))

    with pytest.raises(InvalidProjectError):
        StartServices(FakeFileSystem({}), initialised(), starter).execute(StartServicesCommand(".", 30))


def test_down_stops_the_services_and_reports_a_compose_failure() -> None:
    compose = FakeCompose()
    StopServices(compose).execute()
    assert compose.down_calls == 1

    with pytest.raises(ComposeFailedError, match="no docker"):
        StopServices(FakeCompose(ComposeError("no docker"))).execute()


def test_status_is_ok_when_the_required_services_answer_even_without_the_web_ui() -> None:
    result = ReportStatus(FakeProbe(down=["web-ui"])).execute()

    assert result.all_required_healthy
    assert [(s.name, s.healthy) for s in result.services][-1] == ("web-ui", False)


def test_status_is_not_ok_when_a_required_service_is_down() -> None:
    assert not ReportStatus(FakeProbe(down=["core-service"])).execute().all_required_healthy


def test_open_gives_the_address_without_the_token() -> None:
    result = OpenBrowser(FakeFileSystem(), initialised()).execute(OpenBrowserCommand("."))

    assert result.address == "http://127.0.0.1:8080" and token(5).value not in repr(result)


def test_open_without_a_token_asks_for_init() -> None:
    with pytest.raises(NotInitializedError):
        OpenBrowser(FakeFileSystem(), InMemoryStateStore()).execute(OpenBrowserCommand("."))
