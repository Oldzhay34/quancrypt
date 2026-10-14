package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKeyAgreementDetector;
import org.junit.jupiter.api.Test;

class JcaKeyAgreementDetectorTest {

    private final JcaKeyAgreementDetector detector = new JcaKeyAgreementDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String call) {
        return DetectorHarness.run(detector, "src/main/java/Agree.java", """
                import javax.crypto.KeyAgreement;

                class Agree {
                    void agree() throws Exception {
                        %s
                    }
                }
                """.replace("%s", call));
    }

    @Test
    void ecdhDhAndX25519AreKeyAgreements() {
        assertThat(run("KeyAgreement.getInstance(\"ECDH\");").only().algorithm().family()).isEqualTo(AlgorithmFamily.ECDH);
        assertThat(run("KeyAgreement.getInstance(\"DH\");").only().algorithm().family()).isEqualTo(AlgorithmFamily.DH);
        Observation x25519 = run("KeyAgreement.getInstance(\"X25519\");").only();
        assertThat(x25519.algorithm().family()).isEqualTo(AlgorithmFamily.X25519);
        assertThat(x25519.usage()).isEqualTo(UsageContext.KEY_AGREEMENT);
        assertThat(x25519.detectorId()).isEqualTo("jca.keyagreement");
    }

    @Test
    void anUnknownOrUnresolvedAlgorithmIsUnknown() {
        assertThat(run("KeyAgreement.getInstance(\"Strange\");").unresolved()).containsExactly("Strange");
        assertThat(run("KeyAgreement.getInstance(System.getenv(\"A\"));").only().algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
    }
}

