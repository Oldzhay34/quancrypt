package com.quancrypt.qbank.payment.facade.dto;

/** The fields of a terminal transaction message, all as text. */
public record TerminalTransactionView(
        String transactionId, String terminalId, String accountId, String amount, String currency, String occurredAt) {
}
