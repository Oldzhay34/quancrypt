package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.TlsApiDetector;
import java.util.List;
import org.junit.jupiter.api.Test;

class TlsApiDetectorTest {

    private final TlsApiDetector detector = new TlsApiDetector(DetectorHarness.names());

    private static final String BUNDLES = """
            spring:
              ssl:
                bundle:
                  pem:
                    client:
                      keystore:
                        certificate: "file:${certs}/client.crt.pem"
                        private-key: "file:${certs}/client.key.pem"
            """;

    @Test
    void anSslContextTakesItsKeyFromTheProjectsCertificates() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/java/Tls.java", """
                import javax.net.ssl.SSLContext;

                class Tls {
                    void context() throws Exception {
                        SSLContext.getInstance("TLSv1.2");
                    }
                }
                """, "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        Observation found = outcome.only();
        assertThat(found.usage()).isEqualTo(UsageContext.TLS_KEY_EXCHANGE);
        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.algorithm().keySizeBits()).contains(2048);
        assertThat(found.algorithm().mode()).contains("TLSv1.2");
        assertThat(found.confidence()).isEqualTo(0.5);
        assertThat(found.detectorId()).isEqualTo("java.tls-api");
    }

    @Test
    void withoutAnyCertificateTheFamilyIsUnknownAtLowConfidence() {
        Observation found = DetectorHarness.run(detector, "src/main/java/Tls.java", """
                import javax.net.ssl.SSLContext;

                class Tls {
                    void context() throws Exception {
                        SSLContext.getInstance("TLS");
                    }
                }
                """).only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(found.confidence()).isEqualTo(0.4);
    }

    @Test
    void aSpringSslBundleTakesTheKeyOfItsOwnCertificate() {
        Observation found = DetectorHarness.run(detector, "src/main/java/Client.java", """
                import org.springframework.boot.ssl.SslBundles;

                class Client {
                    static final String BUNDLE = "client";

                    Object context(SslBundles bundles) {
                        return bundles.getBundle(BUNDLE).createSslContext();
                    }
                }
                """, "src/main/resources/application.yml", BUNDLES,
                "certs/client.crt.pem", TestPems.EC_P256_CERTIFICATE).only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(found.algorithm().keySizeBits()).contains(256);
        assertThat(found.confidence()).isEqualTo(0.8);
        assertThat(found.symbol()).isEqualTo("Client#context");
        assertThat(found.library()).contains("spring-boot");
    }

    @Test
    void aTrustManagerThatTrustsEverythingIsAP0Signal() {
        List<Observation> found = DetectorHarness.run(detector, "src/main/java/Insecure.java", """
                import javax.net.ssl.X509TrustManager;
                import java.security.cert.X509Certificate;

                class Insecure implements X509TrustManager {
                    public void checkClientTrusted(X509Certificate[] chain, String type) { }
                    public void checkServerTrusted(X509Certificate[] chain, String type) { }
                    public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
                }
                """).observations();

        assertThat(found).hasSize(1);
        Observation trustAll = found.get(0);
        assertThat(trustAll.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(trustAll.algorithm().rawName()).isEqualTo("TrustManager:trust-all");
        assertThat(trustAll.usage()).isEqualTo(UsageContext.TLS_SERVER_AUTH);
        assertThat(trustAll.priorityOverride()).contains(Priority.P0);
        assertThat(trustAll.symbol()).isEqualTo("Insecure#checkServerTrusted");
    }

    @Test
    void anAnonymousTrustManagerIsFoundToo() {
        Observation found = DetectorHarness.run(detector, "src/main/java/Anon.java", """
                import javax.net.ssl.TrustManager;
                import javax.net.ssl.X509TrustManager;

                class Anon {
                    TrustManager manager() {
                        return new X509TrustManager() {
                            public void checkClientTrusted(java.security.cert.X509Certificate[] c, String t) { }
                            public void checkServerTrusted(java.security.cert.X509Certificate[] c, String t) { }
                            public java.security.cert.X509Certificate[] getAcceptedIssuers() { return null; }
                        };
                    }
                }
                """).only();

        assertThat(found.algorithm().rawName()).isEqualTo("TrustManager:trust-all");
    }

    @Test
    void aTrustManagerThatChecksSomethingIsNotReported() {
        assertThat(DetectorHarness.run(detector, "src/main/java/Checking.java", """
                import javax.net.ssl.X509TrustManager;
                import java.security.cert.CertificateException;
                import java.security.cert.X509Certificate;

                class Checking implements X509TrustManager {
                    public void checkClientTrusted(X509Certificate[] chain, String type) { }
                    public void checkServerTrusted(X509Certificate[] chain, String type) throws CertificateException {
                        if (chain.length == 0) {
                            throw new CertificateException("empty");
                        }
                    }
                    public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
                }
                """).observations()).isEmpty();
    }

    @Test
    void hostnameVerifiersThatAlwaysAgreeAreP0Signals() {
        List<Observation> found = DetectorHarness.run(detector, "src/main/java/Verifiers.java", """
                import javax.net.ssl.HostnameVerifier;
                import javax.net.ssl.HttpsURLConnection;

                class Verifiers {
                    static class Always implements HostnameVerifier {
                        public boolean verify(String host, javax.net.ssl.SSLSession session) {
                            return true;
                        }
                    }

                    void install() {
                        HttpsURLConnection.setDefaultHostnameVerifier((host, session) -> true);
                        HostnameVerifier anonymous = new HostnameVerifier() {
                            public boolean verify(String host, javax.net.ssl.SSLSession session) {
                                return true;
                            }
                        };
                    }
                }
                """).observations();

        assertThat(found).hasSize(3);
        assertThat(found).extracting(o -> o.algorithm().rawName()).containsOnly("HostnameVerifier:allow-all");
        assertThat(found).extracting(Observation::priorityOverride).containsOnly(java.util.Optional.of(Priority.P0));
    }

    @Test
    void aHostnameVerifierThatChecksIsNotReported() {
        assertThat(DetectorHarness.run(detector, "src/main/java/Careful.java", """
                import javax.net.ssl.HostnameVerifier;

                class Careful {
                    HostnameVerifier verifier() {
                        return (host, session) -> host.endsWith(".example.org");
                    }
                }
                """).observations()).isEmpty();
    }

    @Test
    void wellKnownTrustAllConstantsAreFound() {
        List<Observation> found = DetectorHarness.run(detector, "src/main/java/Constants.java", """
                class Constants {
                    Object a = InsecureTrustManagerFactory.INSTANCE;
                    Object b = NoopHostnameVerifier.INSTANCE;
                }
                """).observations();

        assertThat(found).extracting(o -> o.algorithm().rawName()).containsExactlyInAnyOrder("TrustManager:trust-all",
                "HostnameVerifier:allow-all");
        assertThat(found).extracting(Observation::symbol).containsOnly("Constants#a", "Constants#b");
    }

    @Test
    void aProtocolNameThatDoesNotLookLikeOneIsNotCopiedIntoTheFinding() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/java/Tls.java", """
                import javax.net.ssl.SSLContext;

                class Tls {
                    void context() throws Exception {
                        SSLContext.getInstance("not a protocol = really");
                    }
                }
                """);

        assertThat(outcome.only().algorithm().rawName()).isEqualTo("SSLContext:unrecognized");
    }
}
