package com.quancrypt.qbank.payment.domain.model;

import java.util.Objects;

/** A receipt signature: the JCA algorithm name, the signing key id and the base64 signature. */
public record ReceiptSignature(String algorithm, String keyId, String signature) {

    public ReceiptSignature {
        Objects.requireNonNull(algorithm, "algorithm");
        Objects.requireNonNull(keyId, "keyId");
        Objects.requireNonNull(signature, "signature");
        if (algorithm.isBlank() || keyId.isBlank() || signature.isBlank()) {
            throw new IllegalArgumentException("algorithm, key id and signature must not be blank");
        }
    }
}
