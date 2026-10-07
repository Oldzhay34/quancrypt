package com.quancrypt.qbank.payment.domain.model;

import java.util.Objects;

/** The authenticated user who calls the service: the token subject and the bearer token that proves it. */
public record Caller(String username, String bearerToken) {

    public Caller {
        Objects.requireNonNull(username, "username");
        Objects.requireNonNull(bearerToken, "bearerToken");
        if (username.isBlank() || bearerToken.isBlank()) {
            throw new IllegalArgumentException("username and bearer token must not be blank");
        }
    }

    @Override
    public String toString() {
        return "Caller[username=" + username + ", bearerToken=****]";
    }
}
