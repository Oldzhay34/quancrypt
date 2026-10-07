package com.quancrypt.qbank.payment.domain.model;

import java.util.Objects;
import java.util.regex.Pattern;

/** Identifier of an account: 1 to 64 characters from {@code [A-Za-z0-9._-]}. */
public record AccountId(String value) {

    private static final int MAX_LENGTH = 64;
    private static final Pattern ALLOWED = Pattern.compile("[A-Za-z0-9._-]+");

    public AccountId {
        Objects.requireNonNull(value, "value");
        if (value.length() > MAX_LENGTH || !ALLOWED.matcher(value).matches()) {
            throw new IllegalArgumentException("account id must be 1 to " + MAX_LENGTH + " characters from A-Z a-z 0-9 . _ -");
        }
    }
}
