from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable

import pytest

from field_device_sim.api.cli import RunningApplication, build_parser, main, run_loop
from field_device_sim.facade.errors import PublishFailedError
from field_device_sim.facade.health_facade import HealthFacade
from field_device_sim.facade.terminal_facade import PublishedView, TerminalFacade
from field_device_sim.usecase.check_health import CheckHealth
from support.fakes import FixedClock, RecordingStatusReporter


class ScriptedFacade(TerminalFacade):
    """A facade that publishes a fixed number of times, then stops the loop."""

    def __init__(self, stop: threading.Event, stop_after: int, fail_first: int = 0) -> None:
        self.stop = stop
        self.stop_after = stop_after
        self.fail_first = fail_first
        self.calls: list[str] = []

    def publish_next(self, terminal_id: str) -> PublishedView:
        self.calls.append(terminal_id)
        if len(self.calls) >= self.stop_after:
            self.stop.set()
        if len(self.calls) <= self.fail_first:
            raise PublishFailedError("not delivered: the broker is unavailable")
        return PublishedView(f"id-{len(self.calls)}", "acc-001", "12.50", "TRY")


def test_the_run_command_has_the_documented_defaults() -> None:
    args = build_parser().parse_args(["run", "--terminal-id", "terminal-001"])

    assert (args.command, args.terminal_id, args.interval, args.seed) == ("run", "terminal-001", 5.0, None)


def test_the_run_command_needs_a_terminal_id() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run"])


@pytest.mark.parametrize("terminal_id", ["", "../terminal-001", "terminal/001", "terminal+", "t" * 65])
def test_a_terminal_id_that_is_not_a_plain_name_is_refused(terminal_id: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--terminal-id", terminal_id])


@pytest.mark.parametrize("interval", ["0", "-1", "abc"])
def test_a_non_positive_interval_is_refused(interval: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--terminal-id", "t", "--interval", interval])


def test_the_loop_publishes_until_stopped_and_survives_failures(caplog: pytest.LogCaptureFixture) -> None:
    stop = threading.Event()
    facade = ScriptedFacade(stop, stop_after=3, fail_first=1)

    with caplog.at_level(logging.INFO, logger="field_device_sim.cli"):
        run_loop(facade, "terminal-001", 0.001, stop)

    assert facade.calls == ["terminal-001"] * 3
    messages = [record.getMessage() for record in caplog.records]
    assert sum(message.startswith("publishing failed") for message in messages) == 1
    assert sum(message.startswith("published transaction") for message in messages) == 2


def test_the_loop_does_not_publish_when_already_stopped() -> None:
    stop = threading.Event()
    stop.set()
    facade = ScriptedFacade(stop, stop_after=1)

    run_loop(facade, "terminal-001", 0.001, stop)

    assert facade.calls == []


def _health_factory(age_seconds: float | None) -> Callable[[], HealthFacade]:
    clock = FixedClock()
    status = RecordingStatusReporter()
    if age_seconds is not None:
        status.record_success(clock.now())
        clock.advance(age_seconds)
    return lambda: HealthFacade(CheckHealth(clock, status))


def _unused_application(_terminal_id: str, _seed: int | None) -> RunningApplication:
    raise AssertionError("the health check must not start the simulator")


@pytest.mark.parametrize(("age", "exit_code"), [(None, 1), (10.0, 0), (31.0, 1)])
def test_the_healthcheck_command_sets_the_exit_code(age: float | None, exit_code: int) -> None:
    assert main(["healthcheck"], _unused_application, _health_factory(age)) == exit_code


def test_the_healthcheck_command_accepts_a_maximum_age() -> None:
    assert main(["healthcheck", "--max-age", "60"], _unused_application, _health_factory(31.0)) == 0


def test_the_run_command_starts_the_application_stops_on_sigterm_and_releases_the_connection() -> None:
    closed: list[bool] = []
    seen: dict[str, object] = {}
    stop_after_first = threading.Event()

    class SigtermFacade(TerminalFacade):
        def __init__(self) -> None:
            pass

        def publish_next(self, terminal_id: str) -> PublishedView:
            stop_after_first.set()
            signal.raise_signal(signal.SIGTERM)
            return PublishedView("id-1", "acc-001", "1.00", "TRY")

    def factory(terminal_id: str, seed: int | None) -> RunningApplication:
        seen["arguments"] = (terminal_id, seed)
        return RunningApplication(SigtermFacade(), lambda: closed.append(True))

    previous = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    try:
        code = main(
            ["run", "--terminal-id", "terminal-001", "--interval", "30", "--seed", "42"], factory, _health_factory(None)
        )
    finally:
        signal.signal(signal.SIGTERM, previous[0])
        signal.signal(signal.SIGINT, previous[1])

    assert code == 0
    assert seen["arguments"] == ("terminal-001", 42)
    assert stop_after_first.is_set()
    assert closed == [True]
