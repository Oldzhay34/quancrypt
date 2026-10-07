package com.quancrypt.qbank.payment.infrastructure.crypto;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPublicKey;
import java.util.Arrays;
import java.util.Base64;

/** JWK thumbprint of an RSA public key (RFC 7638), used as the key id. */
public final class JwkThumbprint {

    private static final Base64.Encoder BASE64_URL = Base64.getUrlEncoder().withoutPadding();

    private JwkThumbprint() {
    }

    public static String of(RSAPublicKey key) {
        String canonical = "{\"e\":\"" + encode(key.getPublicExponent()) + "\",\"kty\":\"RSA\",\"n\":\""
                + encode(key.getModulus()) + "\"}";
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8));
            return BASE64_URL.encodeToString(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is not available", e);
        }
    }

    private static String encode(BigInteger value) {
        byte[] bytes = value.toByteArray();
        int start = bytes.length > 1 && bytes[0] == 0 ? 1 : 0;
        return BASE64_URL.encodeToString(Arrays.copyOfRange(bytes, start, bytes.length));
    }
}
