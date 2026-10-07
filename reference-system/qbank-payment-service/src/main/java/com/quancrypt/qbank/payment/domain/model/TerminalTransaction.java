package com.quancrypt.qbank.payment.domain.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

/** A transaction a field terminal reported over MQTT. It carries no card data. */
public record TerminalTransaction(
        UUID transactionId, String terminalId, AccountId accountId, BigDecimal amount, String currency, Instant occurredAt) {

    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");
    private static final int MAX_TERMINAL_ID_LENGTH = 64;

    public TerminalTransaction {
        Objects.requireNonNull(transactionId, "transactionId");
        Objects.requireNonNull(terminalId, "terminalId");
        Objects.requireNonNull(accountId, "accountId");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(occurredAt, "occurredAt");
        if (terminalId.isBlank() || terminalId.length() > MAX_TERMINAL_ID_LENGTH) {
            throw new IllegalArgumentException("terminal id must be 1 to " + MAX_TERMINAL_ID_LENGTH + " characters");
        }
        if (!CURRENCY.matcher(currency).matches()) {
            throw new IllegalArgumentException("currency must be a three letter upper case code");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException e) {
            throw new IllegalArgumentException("amount must have at most two fractional digits");
        }
    }
}
