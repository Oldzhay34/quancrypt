package com.quancrypt.qbank.payment.infrastructure.crypto;

import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.port.outbound.CardTokenizer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.Cipher;

/**
 * Tokenizes a card number by encrypting it with RSA-OAEP under the card token public key. The service holds no
 * private key and cannot reverse a token (D-97). QBank intentionally uses RSA here so that Quancrypt can find it.
 */
public final class RsaOaepCardTokenizer implements CardTokenizer {

    /** The JCA transformation named by the phase prompt; "ECB" is a JCA naming artifact, RSA has no block mode. */
    static final String TRANSFORMATION = "RSA/ECB/OAEPWithSHA-256AndMGF1Padding";
    private static final int REQUIRED_KEY_BITS = 2048;

    private final RSAPublicKey publicKey;

    public RsaOaepCardTokenizer(RSAPublicKey publicKey) {
        this.publicKey = Objects.requireNonNull(publicKey, "publicKey");
        if (publicKey.getModulus().bitLength() != REQUIRED_KEY_BITS) {
            throw new IllegalArgumentException("the card token key must be an RSA-" + REQUIRED_KEY_BITS + " key");
        }
    }

    /** Loads the public key from a PEM file. */
    public static RsaOaepCardTokenizer fromPemFile(Path publicKeyFile) {
        return new RsaOaepCardTokenizer(PemKeyLoader.loadPublicKey(publicKeyFile));
    }

    @Override
    public CardToken tokenize(String cardNumber) {
        if (cardNumber == null || cardNumber.isBlank()) {
            throw new IllegalArgumentException("card number must not be blank");
        }
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, publicKey);
            byte[] ciphertext = cipher.doFinal(cardNumber.getBytes(StandardCharsets.UTF_8));
            return new CardToken(Base64.getEncoder().encodeToString(ciphertext));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("the card number could not be tokenized", e);
        }
    }
}
