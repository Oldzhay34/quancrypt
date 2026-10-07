package com.quancrypt.qbank.payment.facade.dto;

/** The signed fields of a receipt as seen by the api layer. */
public record ReceiptView(String paymentId, String accountId, String amount, String currency, String issuedAt) {
}
