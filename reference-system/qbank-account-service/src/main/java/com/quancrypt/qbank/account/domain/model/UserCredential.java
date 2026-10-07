package com.quancrypt.qbank.account.domain.model;

import java.util.Objects;

/** A user's login credential: username, hashed password and the single account the user owns. */
public record UserCredential(String username, PasswordHash passwordHash, AccountId accountId) {

    private static final int MAX_USERNAME_LENGTH = 64;

    public UserCredential {
        Objects.requireNonNull(username, "username");
        Objects.requireNonNull(passwordHash, "passwordHash");
        Objects.requireNonNull(accountId, "accountId");
        if (username.isBlank() || username.length() > MAX_USERNAME_LENGTH) {
            throw new IllegalArgumentException("username must be 1 to " + MAX_USERNAME_LENGTH + " characters");
        }
    }

    /** Returns true when this user owns the given account. */
    public boolean owns(AccountId other) {
        return accountId.equals(other);
    }
}
