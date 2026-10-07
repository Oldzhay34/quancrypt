package com.quancrypt.qbank.payment.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.infrastructure.crypto.JwkThumbprint;
import com.quancrypt.qbank.payment.infrastructure.crypto.PemKeyLoader;
import com.quancrypt.qbank.payment.infrastructure.crypto.RsaOaepCardTokenizer;
import com.quancrypt.qbank.payment.infrastructure.crypto.Sha1WithRsaReceiptSigner;
import com.quancrypt.qbank.payment.support.TestCertificates;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Signature;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import org.junit.jupiter.api.Test;

/** Round trips with the real demo keys: the card token key pair (RSA-2048) and the receipt key pair (RSA-1024). */
class CryptoRoundTripTest {

    private static final String CARD = "4111111111111111";

    private final RSAPublicKey cardPublic = PemKeyLoader.loadPublicKey(TestCertificates.file("card-token.pub.pem"));
    private final RSAPrivateKey cardPrivate = PemKeyLoader.loadPrivateKey(TestCertificates.file("card-token.key.pem"));
    private final RSAPublicKey receiptPublic = PemKeyLoader.loadPublicKey(TestCertificates.file("receipt-signing.pub.pem"));
    private final RSAPrivateKey receiptPrivate = PemKeyLoader.loadPrivateKey(TestCertificates.file("receipt-signing.key.pem"));

    private byte[] decrypt(String token, OAEPParameterSpec parameters) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        if (parameters == null) {
            cipher.init(Cipher.DECRYPT_MODE, cardPrivate);
        } else {
            cipher.init(Cipher.DECRYPT_MODE, cardPrivate, parameters);
        }
        return cipher.doFinal(Base64.getDecoder().decode(token));
    }

    private boolean verifies(String algorithm, String text, String signatureBase64) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(receiptPublic);
        verifier.update(text.getBytes(StandardCharsets.UTF_8));
        return verifier.verify(Base64.getDecoder().decode(signatureBase64));
    }

    @Test
    void theDemoKeysHaveTheIntendedSizes() {
        assertThat(cardPublic.getModulus().bitLength()).isEqualTo(2048);
        assertThat(receiptPublic.getModulus().bitLength()).isEqualTo(1024);
        assertThat(receiptPrivate.getModulus().bitLength()).isEqualTo(1024);
    }

    @Test
    void aCardTokenDecryptsToTheCardNumberWithTheCardPrivateKey() throws GeneralSecurityException {
        CardToken token = new RsaOaepCardTokenizer(cardPublic).tokenize(CARD);

        assertThat(new String(decrypt(token.value(), null), StandardCharsets.UTF_8)).isEqualTo(CARD);
    }

    @Test
    void theTokenIsARandomizedRsa2048CiphertextThatDoesNotContainTheCardNumber() {
        RsaOaepCardTokenizer tokenizer = new RsaOaepCardTokenizer(cardPublic);

        CardToken first = tokenizer.tokenize(CARD);
        CardToken second = tokenizer.tokenize(CARD);

        assertThat(first).isNotEqualTo(second);
        assertThat(Base64.getDecoder().decode(first.value())).hasSize(256);
        assertThat(first.value()).doesNotContain(CARD);
    }

    @Test
    void theOaepMaskGenerationDigestOfTheTransformationIsSha1() throws GeneralSecurityException {
        // Observed JCA behaviour of "RSA/ECB/OAEPWithSHA-256AndMGF1Padding": OAEP hash SHA-256, MGF1 hash SHA-1.
        String token = new RsaOaepCardTokenizer(cardPublic).tokenize(CARD).value();
        OAEPParameterSpec sha1Mgf = new OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA1, PSource.PSpecified.DEFAULT);
        OAEPParameterSpec sha256Mgf = new OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);

        assertThat(new String(decrypt(token, sha1Mgf), StandardCharsets.UTF_8)).isEqualTo(CARD);
        assertThatThrownBy(() -> decrypt(token, sha256Mgf)).isInstanceOf(GeneralSecurityException.class);
    }

    @Test
    void theTokenizerNeedsAnRsa2048KeyAndANonBlankCardNumber() {
        assertThatThrownBy(() -> new RsaOaepCardTokenizer(receiptPublic)).isInstanceOf(IllegalArgumentException.class);
        RsaOaepCardTokenizer tokenizer = new RsaOaepCardTokenizer(cardPublic);
        assertThatThrownBy(() -> tokenizer.tokenize(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> tokenizer.tokenize(null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void aReceiptSignatureVerifiesWithTheRsa1024PublicKeyAndSha1WithRsa() throws GeneralSecurityException {
        String text = "{\"paymentId\":\"x\"}";
        Sha1WithRsaReceiptSigner signer = new Sha1WithRsaReceiptSigner(receiptPrivate, JwkThumbprint.of(receiptPublic));

        ReceiptSignature signature = signer.sign(text);

        assertThat(signature.algorithm()).isEqualTo("SHA1withRSA");
        assertThat(signature.keyId()).isEqualTo(JwkThumbprint.of(receiptPublic));
        assertThat(Base64.getDecoder().decode(signature.signature())).hasSize(128);
        assertThat(verifies("SHA1withRSA", text, signature.signature())).isTrue();
    }

    @Test
    void theSignatureIsSha1NotSha256() throws GeneralSecurityException {
        String text = "receipt";
        ReceiptSignature signature = new Sha1WithRsaReceiptSigner(receiptPrivate, "kid").sign(text);

        assertThat(verifies("SHA256withRSA", text, signature.signature())).isFalse();
    }

    @Test
    void aChangedTextOrASignatureOfAnotherTextDoesNotVerify() throws GeneralSecurityException {
        Sha1WithRsaReceiptSigner signer = new Sha1WithRsaReceiptSigner(receiptPrivate, "kid");
        ReceiptSignature signature = signer.sign("amount 12.50");
        ReceiptSignature other = signer.sign("amount 99.99");

        assertThat(verifies("SHA1withRSA", "amount 12.51", signature.signature())).isFalse();
        assertThat(verifies("SHA1withRSA", "amount 12.50", other.signature())).isFalse();
    }

    @Test
    void signingTheSameTextTwiceGivesTheSameSignature() {
        Sha1WithRsaReceiptSigner signer = new Sha1WithRsaReceiptSigner(receiptPrivate, "kid");

        assertThat(signer.sign("same").signature()).isEqualTo(signer.sign("same").signature());
    }

    @Test
    void theSignerRejectsBlankInputAndBlankKeyIds() {
        Sha1WithRsaReceiptSigner signer = new Sha1WithRsaReceiptSigner(receiptPrivate, "kid");

        assertThatThrownBy(() -> signer.sign(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> signer.sign(null)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Sha1WithRsaReceiptSigner(receiptPrivate, " ")).isInstanceOf(IllegalArgumentException.class);
    }
}
