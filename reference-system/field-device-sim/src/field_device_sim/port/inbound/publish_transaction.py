"""Inbound port: create one random but consistent test transaction and publish it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PublishTransactionCommand:
    """What to publish: the terminal and the value ranges of the generated transaction (amounts in minor units)."""

    terminal_id: str
    account_ids: tuple[str, ...]
    min_amount_cents: int
    max_amount_cents: int
    currency: str


@dataclass(frozen=True)
class PublishTransactionResult:
    """The transaction that was published."""

    transaction_id: str
    terminal_id: str
    account_id: str
    amount: str
    currency: str


class PublishTransactionUseCase(Protocol):
    """Creates and publishes one transaction."""

    def execute(self, command: PublishTransactionCommand) -> PublishTransactionResult:
        """Create, publish and remember one transaction.

        Raises:
            InvalidRequestError: when the command is invalid or yields an invalid transaction.
            DeliveryFailedError: when delivery failed.
        """
        ...
