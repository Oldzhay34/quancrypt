package com.quancrypt.qbank.payment.api.dto;

/** Request body of POST /api/v1/payments. The card number is a test card number only and is never returned. */
public record CreatePaymentRequest(String accountId, String amount, String currency, String cardNumber) {

    @Override
    public String toString() {
        return "CreatePaymentRequest[accountId=" + accountId + ", amount=" + amount + ", currency=" + currency
                + ", cardNumber=****]";
    }
}
