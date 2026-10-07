package com.quancrypt.qbank.account.infrastructure.security;

import java.nio.file.Path;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Objects;

/** The RSA key pair that signs and verifies access tokens, with its key id. */
public record JwtKeyMaterial(String keyId, RSAPublicKey publicKey, RSAPrivateKey privateKey) {

    public JwtKeyMaterial {
        Objects.requireNonNull(keyId, "keyId");
        Objects.requireNonNull(publicKey, "publicKey");
        Objects.requireNonNull(privateKey, "privateKey");
        if (!publicKey.getModulus().equals(privateKey.getModulus())) {
            throw new IllegalStateException("the public key does not belong to the private key");
        }
    }

    /** Loads the key pair from PEM files; the key id is the JWK thumbprint of the public key. */
    public static JwtKeyMaterial load(Path privateKeyFile, Path publicKeyFile) {
        RSAPublicKey publicKey = PemKeyLoader.loadPublicKey(publicKeyFile);
        RSAPrivateKey privateKey = PemKeyLoader.loadPrivateKey(privateKeyFile);
        return new JwtKeyMaterial(JwkThumbprint.of(publicKey), publicKey, privateKey);
    }

    @Override
    public String toString() {
        return "JwtKeyMaterial[keyId=" + keyId + "]";
    }
}
