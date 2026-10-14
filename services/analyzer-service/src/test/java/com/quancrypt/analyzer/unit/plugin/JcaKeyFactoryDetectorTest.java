package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKeyFactoryDetector;
import org.junit.jupiter.api.Test;

class JcaKeyFactoryDetectorTest {

    private final JcaKeyFactoryDetector detector = new JcaKeyFactoryDetector(DetectorHarness.names());

    @Test
    void aKeyLoaderIsOnlyASupportingObservation() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/java/Loader.java", """
                import java.security.KeyFactory;

                class Loader {
                    void load() throws Exception {
                        KeyFactory.getInstance("RSA");
                        KeyFactory.getInstance("Nothing");
                    }
                }
                """);

        assertThat(outcome.observations()).hasSize(1);
        Observation found = outcome.only();
        assertThat(found.role()).isEqualTo(Role.SUPPORT);
        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.detectorId()).isEqualTo("jca.keyfactory");
    }
}

