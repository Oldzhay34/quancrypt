package com.quancrypt.qbank.payment.port.inbound;

import java.math.BigDecimal;

/**
 * Request to create a payment on behalf of the caller named by {@code username} and proven by {@code bearerToken}.
 * {@code idempotencyKey} may be null. The card number is a test card number only.
 */
public record CreatePaymentCommand(
        String username,
        String bearerToken,
        String idempotencyKey,
        String accountId,
        BigDecimal amount,
        String currency,
        String cardNumber) {

    @Override
    public String toString() {
        return "CreatePaymentCommand[username=" + username + ", bearerToken=****, accountId=" + accountId
                + ", amount=" + amount + ", currency=" + currency + ", cardNumber=****]";
    }
}
