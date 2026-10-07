package com.quancrypt.qbank.account.domain.model;

import java.math.BigInteger;
import java.util.Objects;

/** The public part of an RSA key that verifies issued tokens. */
public record VerificationKey(String keyId, BigInteger modulus, BigInteger exponent) {

    public VerificationKey {
        Objects.requireNonNull(keyId, "keyId");
        Objects.requireNonNull(modulus, "modulus");
        Objects.requireNonNull(exponent, "exponent");
        if (keyId.isBlank()) {
            throw new IllegalArgumentException("key id must not be blank");
        }
        if (modulus.signum() <= 0 || exponent.signum() <= 0) {
            throw new IllegalArgumentException("modulus and exponent must be positive");
        }
    }
}
