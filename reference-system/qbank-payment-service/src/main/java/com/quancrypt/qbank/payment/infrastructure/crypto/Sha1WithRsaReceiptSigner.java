package com.quancrypt.qbank.payment.infrastructure.crypto;

import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.port.outbound.ReceiptSigner;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.Signature;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import java.util.Objects;

/**
 * Signs receipts with SHA1withRSA. QBank intentionally uses a weak RSA-1024 key and a SHA-1 signature here (P0
 * findings that Quancrypt must discover); this class must not be copied outside reference-system.
 */
public final class Sha1WithRsaReceiptSigner implements ReceiptSigner {

    /** The JCA signature algorithm named by the phase prompt (D-92). */
    public static final String ALGORITHM = "SHA1withRSA";

    private final RSAPrivateKey privateKey;
    private final String keyId;

    public Sha1WithRsaReceiptSigner(RSAPrivateKey privateKey, String keyId) {
        this.privateKey = Objects.requireNonNull(privateKey, "privateKey");
        this.keyId = Objects.requireNonNull(keyId, "keyId");
        if (keyId.isBlank()) {
            throw new IllegalArgumentException("key id must not be blank");
        }
    }

    /** Loads the key pair from PEM files and refuses a pair whose halves do not belong together. */
    public static Sha1WithRsaReceiptSigner fromPemFiles(Path publicKeyFile, Path privateKeyFile) {
        RSAPublicKey publicKey = PemKeyLoader.loadPublicKey(publicKeyFile);
        RSAPrivateKey privateKey = PemKeyLoader.loadPrivateKey(privateKeyFile);
        if (!publicKey.getModulus().equals(privateKey.getModulus())) {
            throw new IllegalStateException("receipt-signing public and private key do not belong together");
        }
        return new Sha1WithRsaReceiptSigner(privateKey, JwkThumbprint.of(publicKey));
    }

    @Override
    public ReceiptSignature sign(String signingInput) {
        if (signingInput == null || signingInput.isBlank()) {
            throw new IllegalArgumentException("the text to sign must not be blank");
        }
        try {
            Signature signature = Signature.getInstance(ALGORITHM);
            signature.initSign(privateKey);
            signature.update(signingInput.getBytes(StandardCharsets.UTF_8));
            return new ReceiptSignature(ALGORITHM, keyId, Base64.getEncoder().encodeToString(signature.sign()));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("the receipt could not be signed", e);
        }
    }
}
