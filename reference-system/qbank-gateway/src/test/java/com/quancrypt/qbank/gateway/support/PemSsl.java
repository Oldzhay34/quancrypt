package com.quancrypt.qbank.gateway.support;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Base64;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

/** Builds SSL contexts from the demo PEM files for the test doubles and test clients (in memory, nothing is written). */
public final class PemSsl {

    private static final char[] NO_PASSWORD = new char[0];

    private PemSsl() {
    }

    /** A context that presents the identity (certificate and key) and trusts only the demo CA. */
    public static SSLContext withIdentity(String certificateName, String keyName) {
        return build(identity(certificateName, keyName), caStore());
    }

    /** A context that presents no identity and trusts only the demo CA. */
    public static SSLContext trustOnly() {
        return build(null, caStore());
    }

    private static KeyStore identity(String certificateName, String keyName) {
        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, null);
            store.setKeyEntry(
                    "identity",
                    privateKey(TestCertificates.file(keyName)),
                    NO_PASSWORD,
                    new java.security.cert.Certificate[] {certificate(TestCertificates.file(certificateName))});
            return store;
        } catch (GeneralSecurityException | IOException e) {
            throw new IllegalStateException("cannot build the key store for " + certificateName, e);
        }
    }

    private static KeyStore caStore() {
        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, null);
            store.setCertificateEntry("demo-ca", certificate(TestCertificates.file("ca.crt.pem")));
            return store;
        } catch (GeneralSecurityException | IOException e) {
            throw new IllegalStateException("cannot build the trust store", e);
        }
    }

    private static X509Certificate certificate(Path pem) throws GeneralSecurityException, IOException {
        try (InputStream in = Files.newInputStream(pem)) {
            return (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(in);
        }
    }

    private static PrivateKey privateKey(Path pem) throws GeneralSecurityException, IOException {
        String text = Files.readString(pem, StandardCharsets.US_ASCII)
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .replaceAll("\\s", "");
        return KeyFactory.getInstance("RSA")
                .generatePrivate(new PKCS8EncodedKeySpec(Base64.getDecoder().decode(text)));
    }

    private static SSLContext build(KeyStore identity, KeyStore trust) {
        try {
            KeyManagerFactory keys = null;
            if (identity != null) {
                keys = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
                keys.init(identity, NO_PASSWORD);
            }
            TrustManagerFactory trusts = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
            trusts.init(trust);
            SSLContext context = SSLContext.getInstance("TLS");
            context.init(keys == null ? null : keys.getKeyManagers(), trusts.getTrustManagers(), null);
            return context;
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("cannot build the SSL context", e);
        }
    }
}
