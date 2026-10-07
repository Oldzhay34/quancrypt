package com.quancrypt.qbank.payment.domain.model;

import java.util.Objects;

/** What the payment service learns about an account the caller owns. */
public record AccountSummary(AccountId accountId, String currency) {

    public AccountSummary {
        Objects.requireNonNull(accountId, "accountId");
        Objects.requireNonNull(currency, "currency");
    }
}
