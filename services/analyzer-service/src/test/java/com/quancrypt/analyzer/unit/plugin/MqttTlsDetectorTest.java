package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.MqttTlsDetector;
import java.util.List;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class MqttTlsDetectorTest {

    private final MqttTlsDetector detector = new MqttTlsDetector();

    private static final String PAHO = "import org.eclipse.paho.client.mqttv3.MqttClient;\nimport org.eclipse.paho.client.mqttv3.MqttConnectOptions;\n";

    private DetectorHarness.Outcome run(String imports, String body, String... more) {
        String[] files = new String[more.length + 2];
        files[0] = "src/main/java/Mqtt.java";
        files[1] = imports + """

                class Mqtt {
                    void connect(Object bundles) throws Exception {
                        %s
                    }
                }
                """.replace("%s", body);
        System.arraycopy(more, 0, files, 2, more.length);
        return DetectorHarness.run(detector, files);
    }

    @Test
    void aTlsBrokerUriIsAConnectionOverTls() {
        List<Observation> found = run(PAHO, "new MqttClient(\"ssl://broker.example:8883\", \"id\");", "certs/b.crt.pem",
                TestPems.RSA_2048_CERTIFICATE).observations();

        assertThat(found).hasSize(1);
        Observation uri = found.get(0);
        assertThat(uri.usage()).isEqualTo(UsageContext.TLS_KEY_EXCHANGE);
        assertThat(uri.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(uri.algorithm().rawName()).isEqualTo("ssl://");
        assertThat(uri.library()).contains("paho");
        assertThat(uri.symbol()).isEqualTo("Mqtt#connect");
        assertThat(uri.detectorId()).isEqualTo("mqtt.tls");
    }

    @Test
    void aBareSchemeCheckIsNotAConnection() {
        assertThat(run(PAHO, "boolean ok = \"ssl://host\".startsWith(\"ssl://\");").observations()).hasSize(1);
        assertThat(run(PAHO, "if (url.startsWith(\"ssl://\")) { }").observations()).isEmpty();
    }

    @Test
    void aSocketFactoryFromABundleTakesTheBundlesKey() {
        Observation found = run(PAHO, "new MqttConnectOptions().setSocketFactory(sslBundles.getBundle(\"mq\").createSslContext().getSocketFactory());",
                "src/main/resources/application.yml", """
                        spring:
                          ssl:
                            bundle:
                              pem:
                                mq:
                                  keystore:
                                    certificate: "file:/c/mq.crt.pem"
                        """, "certs/mq.crt.pem", TestPems.EC_P256_CERTIFICATE).only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(found.algorithm().rawName()).isEqualTo("MqttConnectOptions.setSocketFactory");
        assertThat(found.confidence()).isEqualTo(0.8);
    }

    @Test
    void filesWithoutPahoAreIgnored() {
        assertThat(run("", "String u = \"ssl://host:8883\";").observations()).isEmpty();
    }

    @Test
    void aHugeLiteralThatStartsLikeAUriDoesNotStallTheMatching() {
        String literal = "ssl://" + "a".repeat(200_000) + "\\n!";

        DetectorHarness.Outcome outcome = assertTimeoutPreemptively(Duration.ofSeconds(10),
                () -> run(PAHO, "new MqttClient(\"" + literal + "\", \"id\");"));

        assertThat(outcome.observations()).hasSize(1);
    }
}
