package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.SpringSslConfigDetector;
import java.util.Map;
import java.util.stream.Collectors;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class SpringSslConfigDetectorTest {

    private final SpringSslConfigDetector detector = new SpringSslConfigDetector(DetectorHarness.names());

    private static final String YAML = """
            server:
              port: 8443
              ssl:
                bundle: server
                client-auth: need
            spring:
              ssl:
                bundle:
                  pem:
                    server:
                      keystore:
                        certificate: "file:${certs}/server.crt.pem"
                        private-key: "file:${certs}/server.key.pem"
                    client:
                      keystore:
                        certificate: "file:${certs}/client.crt.pem"
                        private-key: "file:${certs}/client.key.pem"
                      truststore:
                        certificate: "file:${certs}/ca.crt.pem"
                    trustonly:
                      truststore:
                        certificate: "file:${certs}/ca.crt.pem"
                  jks:
                    legacy:
                      keystore:
                        location: "file:/x/legacy.jks"
            client:
              http-client:
                ssl:
                  ssl-bundle: client
            app:
              account-url: ${ACCOUNT_URL:https://localhost:9444}
              broker: ssl://broker:8883
              greeting: hello
            management:
              server:
                ssl:
                  enabled: false
            """;

    private Map<String, Observation> bySymbol(DetectorHarness.Outcome outcome) {
        return outcome.observations().stream().collect(Collectors.toMap(Observation::symbol, o -> o, (a, b) -> a));
    }

    private DetectorHarness.Outcome run(String yaml) {
        return DetectorHarness.run(detector, "src/main/resources/application.yml", yaml,
                "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/client.crt.pem", TestPems.EC_P256_CERTIFICATE,
                "certs/ca.crt.pem", TestPems.RSA_2048_CERTIFICATE);
    }

    @Test
    void theServerBundleIsTheServersCertificateAndTheKeyComesFromItsFile() {
        Map<String, Observation> found = bySymbol(run(YAML));

        Observation reference = found.get("server.ssl.bundle");
        assertThat(reference.usage()).isEqualTo(UsageContext.TLS_KEY_EXCHANGE);
        assertThat(reference.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(reference.algorithm().keySizeBits()).contains(2048);
        assertThat(reference.confidence()).isEqualTo(0.8);
        assertThat(reference.evidence().lines().orElseThrow().start()).isEqualTo(4);
        assertThat(reference.evidence().locationKind()).isEqualTo(LocationKind.CONFIG);

        Observation bundle = found.get("spring.ssl.bundle.pem.server");
        assertThat(bundle.usage()).isEqualTo(UsageContext.CERTIFICATE);
        assertThat(bundle.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
    }

    @Test
    void aBundleThatTheServerDoesNotUseButHasAKeystoreIsAClientIdentity() {
        Observation client = bySymbol(run(YAML)).get("spring.ssl.bundle.pem.client");

        assertThat(client.usage()).isEqualTo(UsageContext.MTLS_CLIENT_AUTH);
        assertThat(client.algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(client.algorithm().keySizeBits()).contains(256);
    }

    @Test
    void aBundleWithOnlyATruststoreHasNoIdentityOfItsOwn() {
        assertThat(bySymbol(run(YAML))).doesNotContainKey("spring.ssl.bundle.pem.trustonly");
    }

    @Test
    void clientAuthNeedOrWantIsMutualTlsWithTheServersKey() {
        Observation clientAuth = bySymbol(run(YAML)).get("server.ssl.client-auth");

        assertThat(clientAuth.usage()).isEqualTo(UsageContext.MTLS_CLIENT_AUTH);
        assertThat(clientAuth.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(bySymbol(run("server:\n  ssl:\n    client-auth: none\n"))).isEmpty();
        assertThat(bySymbol(run("server:\n  ssl:\n    client-auth: want\n"))).containsKey("server.ssl.client-auth");
    }

    @Test
    void aClientSideBundleReferenceIsATlsConnectionWithThatBundlesKey() {
        Observation reference = bySymbol(run(YAML)).get("client.http-client.ssl.ssl-bundle");

        assertThat(reference.usage()).isEqualTo(UsageContext.TLS_KEY_EXCHANGE);
        assertThat(reference.algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
    }

    @Test
    void jksBundlesAreKeystoreAssetsAndTheirContentIsNotRead() {
        Observation legacy = bySymbol(run(YAML)).get("spring.ssl.bundle.jks.legacy");

        assertThat(legacy.usage()).isEqualTo(UsageContext.KEYSTORE);
        assertThat(legacy.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
    }

    @Test
    void httpsAndSslUrlsWithPlaceholderDefaultsAreTlsConnections() {
        Map<String, Observation> found = bySymbol(run(YAML));

        assertThat(found.get("app.account-url").algorithm().rawName()).isEqualTo("https://");
        assertThat(found.get("app.broker").algorithm().rawName()).isEqualTo("ssl://");
        assertThat(found.get("app.account-url").algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(found.get("app.account-url").confidence()).isEqualTo(0.4);
    }

    @Test
    void settingsThatAreNotTlsAreNotReported() {
        Map<String, Observation> found = bySymbol(run(YAML));

        assertThat(found).doesNotContainKeys("server.port", "app.greeting", "management.server.ssl.enabled");
    }

    @Test
    void whenAllCertificatesShareAKeyTheUrlsTakeItAtMediumConfidence() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/resources/application.yml",
                "app:\n  url: https://service:9444\n", "certs/a.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/b.crt.pem",
                TestPems.RSA_2048_CERTIFICATE);

        assertThat(outcome.only().algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(outcome.only().confidence()).isEqualTo(0.5);
    }

    @Test
    void propertiesFilesAndProfileDocumentsAreRead() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/resources/application-prod.properties",
                "server.ssl.bundle=prod\nserver.ssl.enabled-protocols=TLSv1.2\nserver.ssl.key-store=classpath:app.p12\n"
                        + "server.ssl.certificate=file:/c/server.crt.pem\n",
                "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE);
        Map<String, Observation> found = bySymbol(outcome);

        assertThat(found.get("server.ssl.enabled-protocols").algorithm().mode()).contains("TLSv1.2");
        assertThat(found.get("server.ssl.key-store").usage()).isEqualTo(UsageContext.KEYSTORE);
        assertThat(found.get("server.ssl.certificate").usage()).isEqualTo(UsageContext.CERTIFICATE);
        assertThat(found.get("server.ssl.certificate").algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found).containsKey("server.ssl.bundle");
    }

    @Test
    void yamlWithAProfileDocumentIsReadInEveryProfile() {
        DetectorHarness.Outcome outcome = run("""
                server:
                  ssl:
                    bundle: server
                ---
                spring:
                  config:
                    activate:
                      on-profile: prod
                server:
                  ssl:
                    bundle: client
                """);

        assertThat(outcome.observations().stream().filter(o -> o.symbol().equals("server.ssl.bundle")).toList()).hasSize(2);
    }

    @Test
    void anUnknownProtocolIsReportedAsUnresolved() {
        assertThat(run("server:\n  ssl:\n    protocol: ZZZ\n").unresolved()).containsExactly("ZZZ");
    }

    @Test
    void aHugeValueThatStartsLikeAnUrlDoesNotStallTheMatching() {
        String yaml = "client:\n  url: \"https://" + "a".repeat(200_000) + "\\n!\"\n";

        DetectorHarness.Outcome outcome = assertTimeoutPreemptively(Duration.ofSeconds(10),
                () -> DetectorHarness.run(detector, "src/main/resources/application.yml", yaml));

        assertThat(outcome.observations()).hasSize(1);
    }
}
