package com.quancrypt.qbank.account.api.dto;

/** Response body of GET /api/v1/accounts/{accountId}. */
public record AccountResponse(String accountId, String ownerName, String currency, String balance) {
}
