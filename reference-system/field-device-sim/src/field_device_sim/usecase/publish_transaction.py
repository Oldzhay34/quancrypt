"""Use case: create one random but consistent test transaction and publish it."""

from __future__ import annotations

from decimal import Decimal

from field_device_sim.domain.terminal_transaction import InvalidTransactionError, TerminalTransaction
from field_device_sim.port.inbound.errors import DeliveryFailedError, InvalidRequestError
from field_device_sim.port.inbound.publish_transaction import PublishTransactionCommand, PublishTransactionResult
from field_device_sim.port.outbound.clock import Clock
from field_device_sim.port.outbound.id_generator import IdGenerator
from field_device_sim.port.outbound.message_publisher import MessagePublisher, PublishError
from field_device_sim.port.outbound.random_source import RandomSource
from field_device_sim.port.outbound.status_reporter import StatusReporter


class PublishTransaction:
    """Implements PublishTransactionUseCase."""

    def __init__(
        self,
        publisher: MessagePublisher,
        clock: Clock,
        ids: IdGenerator,
        random: RandomSource,
        status: StatusReporter,
    ) -> None:
        self._publisher = publisher
        self._clock = clock
        self._ids = ids
        self._random = random
        self._status = status

    def execute(self, command: PublishTransactionCommand) -> PublishTransactionResult:
        if not command.account_ids:
            raise InvalidRequestError("at least one account id is needed")
        if not 0 <= command.min_amount_cents <= command.max_amount_cents:
            raise InvalidRequestError("the amount range must satisfy 0 <= minimum <= maximum")
        cents = self._random.integer(command.min_amount_cents, command.max_amount_cents)
        try:
            transaction = TerminalTransaction(
                transaction_id=self._ids.new_id(),
                terminal_id=command.terminal_id,
                account_id=self._random.pick(command.account_ids),
                amount=Decimal(cents).scaleb(-2),
                currency=command.currency,
                occurred_at=self._clock.now(),
            )
        except InvalidTransactionError as error:
            raise InvalidRequestError(str(error)) from error
        try:
            self._publisher.publish(transaction)
        except PublishError as error:
            raise DeliveryFailedError(str(error)) from error
        self._status.record_success(self._clock.now())
        return PublishTransactionResult(
            transaction_id=transaction.transaction_id,
            terminal_id=transaction.terminal_id,
            account_id=transaction.account_id,
            amount=f"{transaction.amount:.2f}",
            currency=transaction.currency,
        )
