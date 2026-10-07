"""The only domain object of the simulator: one transaction of a field terminal."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

# A terminal id becomes a segment of the MQTT topic, so it must not contain "/", "+" or "#".
_TERMINAL_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_ACCOUNT_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_CURRENCY = re.compile(r"[A-Z]{3}")


class InvalidTransactionError(ValueError):
    """A transaction field violates the QBank terminal transaction contract."""


@dataclass(frozen=True)
class TerminalTransaction:
    """A card payment seen by a terminal; it carries no card data (contracts/terminal-transaction.schema.json)."""

    transaction_id: str
    terminal_id: str
    account_id: str
    amount: Decimal
    currency: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        try:
            parsed = uuid.UUID(self.transaction_id)
        except ValueError as error:
            raise InvalidTransactionError("transaction id must be a UUID") from error
        if str(parsed) != self.transaction_id:
            raise InvalidTransactionError("transaction id must be a lower case UUID in canonical form")
        if not _TERMINAL_ID.fullmatch(self.terminal_id):
            raise InvalidTransactionError("terminal id must be 1 to 64 characters from A-Z a-z 0-9 . _ -")
        if not _ACCOUNT_ID.fullmatch(self.account_id):
            raise InvalidTransactionError("account id must be 1 to 64 characters from A-Z a-z 0-9 . _ -")
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise InvalidTransactionError("amount must be a finite decimal")
        if self.amount.as_tuple().exponent != -2:
            raise InvalidTransactionError("amount must have exactly two fractional digits")
        if self.amount < 0:
            raise InvalidTransactionError("amount must not be negative")
        if not _CURRENCY.fullmatch(self.currency):
            raise InvalidTransactionError("currency must be a three letter upper case code")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() != timedelta(0):
            raise InvalidTransactionError("occurred_at must be a timezone aware UTC time")
