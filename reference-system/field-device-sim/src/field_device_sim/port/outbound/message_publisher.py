"""Outbound port: delivery of a transaction to the broker."""

from __future__ import annotations

from typing import Protocol

from field_device_sim.domain.terminal_transaction import TerminalTransaction


class PublishError(Exception):
    """The transaction could not be delivered (broker unreachable, connection lost, no acknowledgement)."""


class MessagePublisher(Protocol):
    """Delivers transactions; returns once the broker acknowledged the message."""

    def publish(self, transaction: TerminalTransaction) -> None:
        """Deliver the transaction.

        Raises:
            PublishError: when delivery failed.
        """
        ...
