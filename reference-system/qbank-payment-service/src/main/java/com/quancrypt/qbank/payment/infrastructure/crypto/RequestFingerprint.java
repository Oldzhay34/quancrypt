package com.quancrypt.qbank.payment.infrastructure.crypto;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** SHA-256 fingerprint of a request description, so that the description itself never has to be kept. */
public final class RequestFingerprint {

    private RequestFingerprint() {
    }

    public static String of(String description) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(description.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is not available", e);
        }
    }
}
