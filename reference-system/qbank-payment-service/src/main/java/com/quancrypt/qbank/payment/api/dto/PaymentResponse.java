package com.quancrypt.qbank.payment.api.dto;

/** A payment as returned by the API; neither the card number nor its token is part of it. */
public record PaymentResponse(String paymentId, String accountId, String amount, String currency, String createdAt) {
}
