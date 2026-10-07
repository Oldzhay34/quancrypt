from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from field_device_sim.domain.terminal_transaction import InvalidTransactionError, TerminalTransaction

VALID = TerminalTransaction(
    transaction_id="00000000-0000-4000-8000-000000000001",
    terminal_id="terminal-001",
    account_id="acc-001",
    amount=Decimal("12.50"),
    currency="TRY",
    occurred_at=datetime(2026, 10, 7, 10, 15, 30, tzinfo=timezone.utc),
)


def test_a_valid_transaction_is_accepted_and_immutable() -> None:
    assert VALID.amount == Decimal("12.50")
    with pytest.raises(AttributeError):
        VALID.currency = "USD"  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"transaction_id": "not-a-uuid"},
        {"transaction_id": "00000000-0000-4000-8000-00000000000A"},
        {"terminal_id": ""},
        {"terminal_id": "terminal/001"},
        {"terminal_id": "terminal+"},
        {"terminal_id": "#"},
        {"terminal_id": "t" * 65},
        {"account_id": ""},
        {"account_id": "acc 001"},
        {"account_id": "a" * 65},
        {"amount": Decimal("12.5")},
        {"amount": Decimal("12.500")},
        {"amount": Decimal("-1.00")},
        {"amount": Decimal("NaN")},
        {"currency": "try"},
        {"currency": "TR"},
        {"occurred_at": datetime(2026, 10, 7, 10, 15, 30)},
        {"occurred_at": datetime(2026, 10, 7, 10, 15, 30, tzinfo=timezone(timedelta(hours=3)))},
    ],
    ids=lambda changes: next(iter(changes)) + "=" + str(next(iter(changes.values()))),
)
def test_an_invalid_field_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidTransactionError):
        replace(VALID, **changes)  # type: ignore[arg-type]


def test_the_largest_demo_values_are_accepted() -> None:
    assert replace(VALID, amount=Decimal("0.00"), terminal_id="t" * 64, account_id="a" * 64)
