package com.quancrypt.qbank.account.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.jwk.RSAKey;
import com.quancrypt.qbank.account.infrastructure.security.JwkThumbprint;
import com.quancrypt.qbank.account.infrastructure.security.JwtKeyMaterial;
import com.quancrypt.qbank.account.infrastructure.security.PemKeyLoader;
import com.quancrypt.qbank.account.support.TestCertificates;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.interfaces.RSAPublicKey;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class KeyLoadingTest {

    @TempDir
    Path tempDir;

    @Test
    void loadsTheDemoKeyPair() {
        JwtKeyMaterial keys = JwtKeyMaterial.load(
                TestCertificates.file("jwt-signing.key.pem"), TestCertificates.file("jwt-signing.pub.pem"));

        assertThat(keys.publicKey().getModulus().bitLength()).isEqualTo(2048);
        assertThat(keys.keyId()).isEqualTo(JwkThumbprint.of(keys.publicKey()));
    }

    @Test
    void thumbprintMatchesTheNimbusImplementationOfRfc7638() throws JOSEException {
        RSAPublicKey publicKey = PemKeyLoader.loadPublicKey(TestCertificates.file("jwt-signing.pub.pem"));

        String expected = new RSAKey.Builder(publicKey).build().computeThumbprint().toString();

        assertThat(JwkThumbprint.of(publicKey)).isEqualTo(expected);
    }

    @Test
    void aPublicKeyThatDoesNotBelongToThePrivateKeyIsRejected() {
        Path privateKey = TestCertificates.file("jwt-signing.key.pem");
        Path otherPublicKey = TestCertificates.file("card-token.pub.pem");

        assertThatThrownBy(() -> JwtKeyMaterial.load(privateKey, otherPublicKey))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("does not belong");
    }

    @Test
    void aPrivateKeyIsNotAcceptedAsAPublicKeyAndTheMessageNamesOnlyTheFile() {
        Path privateKey = TestCertificates.file("jwt-signing.key.pem");

        assertThatThrownBy(() -> PemKeyLoader.loadPublicKey(privateKey))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("jwt-signing.key.pem")
                // the message may name the expected PEM header, but never any base64 key material
                .hasMessageNotContaining("MII")
                .message().doesNotContainPattern("[A-Za-z0-9+/=]{40,}");
    }

    @Test
    void aCertificateIsNotAcceptedAsAKey() {
        Path certificate = TestCertificates.file("ca.crt.pem");

        assertThatThrownBy(() -> PemKeyLoader.loadPrivateKey(certificate)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> PemKeyLoader.loadPublicKey(certificate)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void aMissingFileFailsWithTheFileName() {
        Path missing = tempDir.resolve("nope.key.pem");

        assertThatThrownBy(() -> PemKeyLoader.loadPrivateKey(missing))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("nope.key.pem");
    }

    @Test
    void invalidBase64AndInvalidKeyBytesAreRejectedWithoutLeakingContent() throws IOException {
        Path badBase64 = Files.writeString(
                tempDir.resolve("bad64.pem"), "-----BEGIN PRIVATE KEY-----\n!!!not-base64!!!\n-----END PRIVATE KEY-----\n");
        Path badKey = Files.writeString(
                tempDir.resolve("badkey.pem"), "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n");

        assertThatThrownBy(() -> PemKeyLoader.loadPrivateKey(badBase64))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageNotContaining("not-base64");
        assertThatThrownBy(() -> PemKeyLoader.loadPrivateKey(badKey))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("badkey.pem");
    }

    @Test
    void keyMaterialDoesNotPrintTheKeys() {
        JwtKeyMaterial keys = JwtKeyMaterial.load(
                TestCertificates.file("jwt-signing.key.pem"), TestCertificates.file("jwt-signing.pub.pem"));

        assertThat(keys.toString()).startsWith("JwtKeyMaterial[keyId=").doesNotContain("Private");
    }
}
