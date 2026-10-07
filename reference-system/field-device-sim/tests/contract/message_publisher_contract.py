"""Contract of the MessagePublisher port (LSP): every adapter, fake or real, passes the same tests.

A subclass says how to get a working publisher, how to observe what the other side received, and how to get a
publisher whose transport is unavailable.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from field_device_sim.domain.terminal_transaction import TerminalTransaction
from field_device_sim.port.outbound.message_publisher import MessagePublisher, PublishError

TRANSACTION = TerminalTransaction(
    transaction_id="00000000-0000-4000-8000-000000000001",
    terminal_id="terminal-001",
    account_id="acc-001",
    amount=Decimal("12.50"),
    currency="TRY",
    occurred_at=datetime(2026, 10, 7, 10, 15, 30, tzinfo=timezone.utc),
)


class MessagePublisherContract:
    """Subclass and implement the three hooks."""

    def publisher(self) -> MessagePublisher:
        raise NotImplementedError

    def unavailable_publisher(self) -> MessagePublisher:
        raise NotImplementedError

    def delivered(self) -> list[TerminalTransaction]:
        """What the receiving side got, in arrival order."""
        raise NotImplementedError

    def wait_for_delivered(self, count: int, timeout_seconds: float = 10) -> list[TerminalTransaction]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            received = self.delivered()
            if len(received) >= count:
                return received
            time.sleep(0.05)
        return self.delivered()

    def test_a_published_transaction_arrives_unchanged(self) -> None:
        self.publisher().publish(TRANSACTION)

        assert self.wait_for_delivered(1) == [TRANSACTION]

    def test_transactions_arrive_in_the_order_they_were_published(self) -> None:
        publisher = self.publisher()
        transactions = [
            replace(
                TRANSACTION, transaction_id=f"00000000-0000-4000-8000-00000000001{index}", amount=Decimal(f"{index}.00")
            )
            for index in range(3)
        ]

        for transaction in transactions:
            publisher.publish(transaction)

        assert self.wait_for_delivered(3) == transactions

    def test_an_unavailable_transport_is_reported_as_publish_error(self) -> None:
        with pytest.raises(PublishError):
            self.unavailable_publisher().publish(TRANSACTION)

        assert self.delivered() == []
