package com.quancrypt.qbank.payment.port.inbound;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** A signed receipt as returned to the caller. */
public record SignedReceiptResult(UUID paymentId, ReceiptData receipt, String signature, String algorithm, String keyId) {

    /** The signed receipt fields. */
    public record ReceiptData(UUID paymentId, String accountId, BigDecimal amount, String currency, Instant issuedAt) {
    }
}
