package com.quancrypt.qbank.payment.port.inbound;

import java.util.UUID;

/** Request to issue a receipt for the caller named by {@code username}. {@code idempotencyKey} may be null. */
public record IssueReceiptCommand(String username, String idempotencyKey, UUID paymentId) {
}
