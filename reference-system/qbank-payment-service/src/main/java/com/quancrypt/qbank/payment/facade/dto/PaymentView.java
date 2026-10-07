package com.quancrypt.qbank.payment.facade.dto;

/** A payment as seen by the api layer: decimal and time values are already text. */
public record PaymentView(String paymentId, String accountId, String amount, String currency, String createdAt) {
}
