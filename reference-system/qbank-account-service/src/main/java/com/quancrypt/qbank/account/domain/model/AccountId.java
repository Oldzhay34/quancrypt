package com.quancrypt.qbank.account.domain.model;

import java.util.Objects;

/** Identifier of an account: 1 to 64 characters. */
public record AccountId(String value) {

    private static final int MAX_LENGTH = 64;

    public AccountId {
        Objects.requireNonNull(value, "value");
        if (value.isBlank() || value.length() > MAX_LENGTH) {
            throw new IllegalArgumentException("account id must be 1 to " + MAX_LENGTH + " characters");
        }
    }
}
