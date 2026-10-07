package com.quancrypt.qbank.payment.port.inbound;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** A transaction reported by a terminal. */
public record RecordTerminalTransactionCommand(
        UUID transactionId, String terminalId, String accountId, BigDecimal amount, String currency, Instant occurredAt) {
}
