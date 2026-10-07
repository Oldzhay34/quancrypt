from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from field_device_sim.port.inbound.errors import DeliveryFailedError, InvalidRequestError
from field_device_sim.port.inbound.publish_transaction import PublishTransactionCommand
from field_device_sim.usecase.publish_transaction import PublishTransaction
from support.fakes import (
    START,
    FakeMessagePublisher,
    FixedClock,
    RecordingStatusReporter,
    ScriptedRandomSource,
    SequentialIdGenerator,
)

COMMAND = PublishTransactionCommand(
    terminal_id="terminal-001",
    account_ids=("acc-001", "acc-002", "acc-003"),
    min_amount_cents=100,
    max_amount_cents=50_000,
    currency="TRY",
)


def make(
    publisher: FakeMessagePublisher | None = None, random: ScriptedRandomSource | None = None
) -> tuple[PublishTransaction, FakeMessagePublisher, RecordingStatusReporter, FixedClock]:
    fake = publisher or FakeMessagePublisher()
    status = RecordingStatusReporter()
    clock = FixedClock()
    return (
        PublishTransaction(fake, clock, SequentialIdGenerator(), random or ScriptedRandomSource(), status),
        fake,
        status,
        clock,
    )


def test_it_publishes_a_transaction_built_from_the_ports() -> None:
    use_case, publisher, _, _ = make(random=ScriptedRandomSource(picks=[2], integers=[1250]))

    result = use_case.execute(COMMAND)

    assert len(publisher.published) == 1
    transaction = publisher.published[0]
    assert transaction.transaction_id == "00000000-0000-4000-8000-000000000001"
    assert transaction.terminal_id == "terminal-001"
    assert transaction.account_id == "acc-003"
    assert transaction.amount == Decimal("12.50")
    assert transaction.currency == "TRY"
    assert transaction.occurred_at == START
    assert (result.transaction_id, result.account_id, result.amount) == (transaction.transaction_id, "acc-003", "12.50")


def test_the_amount_always_has_two_fractional_digits() -> None:
    use_case, publisher, _, _ = make(random=ScriptedRandomSource(integers=[100]))

    use_case.execute(COMMAND)

    assert str(publisher.published[0].amount) == "1.00"
    assert use_case.execute(replace(COMMAND, min_amount_cents=0, max_amount_cents=0)).amount == "0.00"


def test_each_call_creates_a_new_transaction_id_and_remembers_the_success() -> None:
    use_case, publisher, status, clock = make()

    use_case.execute(COMMAND)
    clock.advance(5)
    use_case.execute(COMMAND)

    assert [t.transaction_id for t in publisher.published] == [
        "00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000002",
    ]
    assert status.successes == [START, clock.now()]


def test_a_failed_delivery_is_reported_and_not_remembered_as_success() -> None:
    use_case, _, status, _ = make(publisher=FakeMessagePublisher(failing=True))

    with pytest.raises(DeliveryFailedError):
        use_case.execute(COMMAND)

    assert status.successes == []


@pytest.mark.parametrize(
    "command",
    [
        replace(COMMAND, account_ids=()),
        replace(COMMAND, min_amount_cents=500, max_amount_cents=100),
        replace(COMMAND, min_amount_cents=-1),
        replace(COMMAND, terminal_id="terminal/001"),
        replace(COMMAND, currency="try"),
    ],
)
def test_an_invalid_command_is_rejected_before_anything_is_published(command: PublishTransactionCommand) -> None:
    use_case, publisher, status, _ = make()

    with pytest.raises(InvalidRequestError):
        use_case.execute(command)

    assert publisher.published == []
    assert status.successes == []
