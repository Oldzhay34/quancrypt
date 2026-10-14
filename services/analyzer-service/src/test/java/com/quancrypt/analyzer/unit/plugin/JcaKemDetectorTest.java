package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKemDetector;
import org.junit.jupiter.api.Test;

class JcaKemDetectorTest {

    private final JcaKemDetector detector = new JcaKemDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String call) {
        return DetectorHarness.run(detector, "src/main/java/Kem.java", """
                import javax.crypto.KEM;

                class Kem {
                    void encapsulate() throws Exception {
                        %s
                    }
                }
                """.replace("%s", call));
    }

    @Test
    void mlKemIsQuantumResistantAndDhKemIsNot() {
        Observation mlKem = run("KEM.getInstance(\"ML-KEM-768\");").only();
        Observation dhKem = run("KEM.getInstance(\"DHKEM\");").only();

        assertThat(mlKem.algorithm().family()).isEqualTo(AlgorithmFamily.ML_KEM);
        assertThat(mlKem.usage()).isEqualTo(UsageContext.KEY_AGREEMENT);
        assertThat(mlKem.detectorId()).isEqualTo("jca.kem");
        assertThat(dhKem.algorithm().family()).isEqualTo(AlgorithmFamily.ECDH);
    }

    @Test
    void anotherKemClassIsIgnored() {
        assertThat(DetectorHarness.run(detector, "src/main/java/Other.java", """
                import com.acme.KEM;

                class Other {
                    void run() {
                        KEM.getInstance("ML-KEM");
                    }
                }
                """).observations()).isEmpty();
    }
}

