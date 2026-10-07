from __future__ import annotations

import pytest

from field_device_sim.facade.errors import PublishFailedError
from field_device_sim.facade.health_facade import HealthFacade
from field_device_sim.facade.terminal_facade import DEMO_ACCOUNT_IDS, TerminalFacade
from field_device_sim.port.inbound.check_health import CheckHealthQuery
from field_device_sim.usecase.check_health import CheckHealth
from field_device_sim.usecase.publish_transaction import PublishTransaction
from support.fakes import (
    FakeMessagePublisher,
    FixedClock,
    RecordingStatusReporter,
    ScriptedRandomSource,
    SequentialIdGenerator,
)


def test_without_a_publication_the_simulator_is_unhealthy() -> None:
    result = CheckHealth(FixedClock(), RecordingStatusReporter()).execute(CheckHealthQuery(30))

    assert not result.healthy
    assert "no successful publication" in result.reason


def test_a_recent_publication_is_healthy_and_an_old_one_is_not() -> None:
    clock = FixedClock()
    status = RecordingStatusReporter()
    status.record_success(clock.now())
    check = CheckHealth(clock, status)

    clock.advance(30)
    assert check.execute(CheckHealthQuery(30)).healthy

    clock.advance(1)
    stale = check.execute(CheckHealthQuery(30))
    assert not stale.healthy
    assert "31 s ago" in stale.reason


def test_the_health_facade_translates_the_result() -> None:
    clock = FixedClock()
    status = RecordingStatusReporter()
    status.record_success(clock.now())

    view = HealthFacade(CheckHealth(clock, status)).health(30)

    assert view.healthy
    assert view.reason == "last successful publication was 0 s ago"


def _terminal_facade(publisher: FakeMessagePublisher, random: ScriptedRandomSource | None = None) -> TerminalFacade:
    use_case = PublishTransaction(
        publisher, FixedClock(), SequentialIdGenerator(), random or ScriptedRandomSource(), RecordingStatusReporter()
    )
    return TerminalFacade(use_case)


def test_the_terminal_facade_publishes_with_the_demo_accounts_and_amount_range() -> None:
    publisher = FakeMessagePublisher()
    facade = _terminal_facade(publisher, ScriptedRandomSource(picks=[1], integers=[50_000]))

    view = facade.publish_next("terminal-001")

    assert view.account_id == DEMO_ACCOUNT_IDS[1] == "acc-002"
    assert view.amount == "500.00"
    assert view.currency == "TRY"
    assert publisher.published[0].transaction_id == view.transaction_id


def test_the_terminal_facade_turns_every_failure_into_publish_failed() -> None:
    with pytest.raises(PublishFailedError, match="not delivered"):
        _terminal_facade(FakeMessagePublisher(failing=True)).publish_next("terminal-001")

    with pytest.raises(PublishFailedError, match="invalid transaction"):
        _terminal_facade(FakeMessagePublisher()).publish_next("terminal/001")
