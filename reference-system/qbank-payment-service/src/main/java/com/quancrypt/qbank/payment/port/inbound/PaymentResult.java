package com.quancrypt.qbank.payment.port.inbound;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** A payment as returned to the caller; it never carries the card number or its token. */
public record PaymentResult(UUID paymentId, String accountId, BigDecimal amount, String currency, Instant createdAt) {
}
