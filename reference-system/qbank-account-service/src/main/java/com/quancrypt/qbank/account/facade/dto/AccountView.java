package com.quancrypt.qbank.account.facade.dto;

/** An account as seen by the api layer; the balance is a decimal string with two fractional digits. */
public record AccountView(String accountId, String ownerName, String currency, String balance) {
}
