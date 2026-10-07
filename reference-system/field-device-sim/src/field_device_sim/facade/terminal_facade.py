"""Coarse-grained entry point of the simulator for the CLI: publishing."""

from __future__ import annotations

from dataclasses import dataclass

from field_device_sim.facade.errors import PublishFailedError
from field_device_sim.port.inbound.errors import DeliveryFailedError, InvalidRequestError
from field_device_sim.port.inbound.publish_transaction import PublishTransactionCommand, PublishTransactionUseCase

# The QBank demo accounts (account service demo data, D-87) and the value range of generated transactions (D-111).
DEMO_ACCOUNT_IDS = ("acc-001", "acc-002", "acc-003")
MIN_AMOUNT_CENTS = 100
MAX_AMOUNT_CENTS = 50_000
CURRENCY = "TRY"


@dataclass(frozen=True)
class PublishedView:
    """A published transaction as the CLI shows it."""

    transaction_id: str
    account_id: str
    amount: str
    currency: str


class TerminalFacade:
    """Publishes transactions for one terminal."""

    def __init__(self, publish: PublishTransactionUseCase) -> None:
        self._publish = publish

    def publish_next(self, terminal_id: str) -> PublishedView:
        command = PublishTransactionCommand(
            terminal_id=terminal_id,
            account_ids=DEMO_ACCOUNT_IDS,
            min_amount_cents=MIN_AMOUNT_CENTS,
            max_amount_cents=MAX_AMOUNT_CENTS,
            currency=CURRENCY,
        )
        try:
            result = self._publish.execute(command)
        except InvalidRequestError as error:
            raise PublishFailedError(f"invalid transaction: {error}") from error
        except DeliveryFailedError as error:
            raise PublishFailedError(f"not delivered: {error}") from error
        return PublishedView(result.transaction_id, result.account_id, result.amount, result.currency)
