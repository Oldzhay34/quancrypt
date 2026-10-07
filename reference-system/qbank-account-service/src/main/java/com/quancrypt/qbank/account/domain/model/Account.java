package com.quancrypt.qbank.account.domain.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;
import java.util.regex.Pattern;

/** A bank account: owner, ISO 4217 currency and a non-negative balance with two fractional digits. */
public record Account(AccountId accountId, String ownerName, String currency, BigDecimal balance) {

    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");

    public Account {
        Objects.requireNonNull(accountId, "accountId");
        Objects.requireNonNull(ownerName, "ownerName");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(balance, "balance");
        if (ownerName.isBlank()) {
            throw new IllegalArgumentException("owner name must not be blank");
        }
        if (!CURRENCY.matcher(currency).matches()) {
            throw new IllegalArgumentException("currency must be a three letter upper case code");
        }
        if (balance.signum() < 0) {
            throw new IllegalArgumentException("balance must not be negative");
        }
        try {
            balance = balance.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException e) {
            throw new IllegalArgumentException("balance must have at most two fractional digits");
        }
    }
}
