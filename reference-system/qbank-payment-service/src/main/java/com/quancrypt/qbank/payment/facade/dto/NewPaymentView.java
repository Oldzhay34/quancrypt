package com.quancrypt.qbank.payment.facade.dto;

/** The fields of a payment request; the card number is a test card number only. */
public record NewPaymentView(String accountId, String amount, String currency, String cardNumber) {

    @Override
    public String toString() {
        return "NewPaymentView[accountId=" + accountId + ", amount=" + amount + ", currency=" + currency
                + ", cardNumber=****]";
    }
}
