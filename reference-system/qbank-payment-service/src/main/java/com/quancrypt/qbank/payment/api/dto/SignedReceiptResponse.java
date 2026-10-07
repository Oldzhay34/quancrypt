package com.quancrypt.qbank.payment.api.dto;

/** Response body of POST /api/v1/payments/{paymentId}/receipt. */
public record SignedReceiptResponse(String paymentId, ReceiptBody receipt, String signature, String algorithm, String keyId) {
}
