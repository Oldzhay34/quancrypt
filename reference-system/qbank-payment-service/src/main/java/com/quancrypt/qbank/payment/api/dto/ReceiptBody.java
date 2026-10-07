package com.quancrypt.qbank.payment.api.dto;

/** The signed fields of a receipt. */
public record ReceiptBody(String paymentId, String accountId, String amount, String currency, String issuedAt) {
}
