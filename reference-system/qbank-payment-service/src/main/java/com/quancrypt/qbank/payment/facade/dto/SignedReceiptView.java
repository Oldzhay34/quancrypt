package com.quancrypt.qbank.payment.facade.dto;

/** A signed receipt as seen by the api layer. */
public record SignedReceiptView(String paymentId, ReceiptView receipt, String signature, String algorithm, String keyId) {
}
