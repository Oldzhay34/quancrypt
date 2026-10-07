package com.quancrypt.qbank.payment.domain.model;

import java.util.Objects;

/** The protected form of a card number (base64 of the RSA-OAEP ciphertext); never the card number itself. */
public record CardToken(String value) {

    public CardToken {
        Objects.requireNonNull(value, "value");
        if (value.isBlank()) {
            throw new IllegalArgumentException("card token must not be blank");
        }
    }

    @Override
    public String toString() {
        return "CardToken[****]";
    }
}
