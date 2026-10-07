package com.quancrypt.qbank.payment.infrastructure.crypto;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

/** Reads unencrypted RSA keys from PEM files: PKCS#8 private keys and X.509 SubjectPublicKeyInfo public keys. */
public final class PemKeyLoader {

    private static final String PRIVATE_BEGIN = "-----BEGIN PRIVATE KEY-----";
    private static final String PRIVATE_END = "-----END PRIVATE KEY-----";
    private static final String PUBLIC_BEGIN = "-----BEGIN PUBLIC KEY-----";
    private static final String PUBLIC_END = "-----END PUBLIC KEY-----";

    private PemKeyLoader() {
    }

    /** Loads an RSA private key; fails fast with a message that never contains key material. */
    public static RSAPrivateKey loadPrivateKey(Path file) {
        byte[] der = decode(file, PRIVATE_BEGIN, PRIVATE_END);
        try {
            if (KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(der)) instanceof RSAPrivateKey key) {
                return key;
            }
        } catch (GeneralSecurityException e) {
            throw unreadable(file, "not a valid PKCS#8 RSA private key");
        }
        throw unreadable(file, "not an RSA private key");
    }

    /** Loads an RSA public key; fails fast with a message that never contains key material. */
    public static RSAPublicKey loadPublicKey(Path file) {
        byte[] der = decode(file, PUBLIC_BEGIN, PUBLIC_END);
        try {
            if (KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(der)) instanceof RSAPublicKey key) {
                return key;
            }
        } catch (GeneralSecurityException e) {
            throw unreadable(file, "not a valid RSA public key");
        }
        throw unreadable(file, "not an RSA public key");
    }

    private static byte[] decode(Path file, String begin, String end) {
        String pem;
        try {
            pem = Files.readString(file, StandardCharsets.US_ASCII).strip();
        } catch (IOException e) {
            throw unreadable(file, "file cannot be read");
        }
        if (!pem.startsWith(begin) || !pem.endsWith(end)) {
            throw unreadable(file, "expected PEM header " + begin);
        }
        String body = pem.substring(begin.length(), pem.length() - end.length()).replaceAll("\\s", "");
        try {
            return Base64.getDecoder().decode(body);
        } catch (IllegalArgumentException e) {
            throw unreadable(file, "PEM body is not valid base64");
        }
    }

    private static IllegalStateException unreadable(Path file, String reason) {
        return new IllegalStateException("cannot load key file " + file.getFileName() + ": " + reason);
    }
}
