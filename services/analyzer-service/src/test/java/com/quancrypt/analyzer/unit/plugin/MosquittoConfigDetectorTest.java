package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.MosquittoConfigDetector;
import java.util.List;
import org.junit.jupiter.api.Test;

class MosquittoConfigDetectorTest {

    private final MosquittoConfigDetector detector = new MosquittoConfigDetector(DetectorHarness.names());

    private static final String CONF = """
            # broker
            listener 8883
            cafile /mosquitto/certs/ca.crt.pem
            certfile /mosquitto/certs/mosquitto.crt.pem
            keyfile /mosquitto/certs/mosquitto.key.pem
            require_certificate true
            use_identity_as_username true
            tls_version tlsv1.2
            """;

    @Test
    void certfileRequireCertificateAndTlsVersionAreTheBrokersTls() {
        List<Observation> found = DetectorHarness.run(detector, "mosquitto/mosquitto.conf", CONF,
                "certs/mosquitto.crt.pem", TestPems.RSA_2048_CERTIFICATE).observations();

        assertThat(found).extracting(Observation::symbol).containsExactly("certfile", "require_certificate", "tls_version");
        assertThat(found.get(0).usage()).isEqualTo(UsageContext.TLS_KEY_EXCHANGE);
        assertThat(found.get(0).algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.get(0).evidence().lines().orElseThrow().start()).isEqualTo(4);
        assertThat(found.get(1).usage()).isEqualTo(UsageContext.MTLS_CLIENT_AUTH);
        assertThat(found.get(1).algorithm().keySizeBits()).contains(2048);
        assertThat(found.get(2).algorithm().mode()).contains("TLSv1.2");
        assertThat(found.get(0).detectorId()).isEqualTo("mosquitto.config");
    }

    @Test
    void aBrokerWithoutTlsHasNothingToReport() {
        assertThat(DetectorHarness.run(detector, "mosquitto/mosquitto.conf", "listener 1883\nallow_anonymous true\nrequire_certificate false\n")
                .observations()).isEmpty();
    }

    @Test
    void otherConfFilesAreNotMosquittoConfigurations() {
        assertThat(DetectorHarness.run(detector, "nginx/nginx.conf", CONF).observations()).isEmpty();
    }
}

