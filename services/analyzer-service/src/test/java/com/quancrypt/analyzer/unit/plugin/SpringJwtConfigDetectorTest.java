package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.SpringJwtConfigDetector;
import java.util.List;
import org.junit.jupiter.api.Test;

class SpringJwtConfigDetectorTest {

    private final SpringJwtConfigDetector detector = new SpringJwtConfigDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String yaml) {
        return DetectorHarness.run(detector, "src/main/resources/application.yml", yaml);
    }

    @Test
    void theAcceptedAlgorithmsAreTokenSignatures() {
        List<Observation> found = run("""
                spring:
                  security:
                    oauth2:
                      resourceserver:
                        jwt:
                          jwk-set-uri: https://idp/jwks
                          jws-algorithms: RS256, ES256
                """).observations();

        assertThat(found).extracting(o -> o.algorithm().family()).containsExactly(AlgorithmFamily.RSA, AlgorithmFamily.ECDSA);
        assertThat(found).extracting(Observation::usage).containsOnly(UsageContext.TOKEN_SIGNATURE);
        assertThat(found.get(0).symbol()).isEqualTo("spring.security.oauth2.resourceserver.jwt.jws-algorithms");
        assertThat(found.get(0).confidence()).isEqualTo(0.9);
        assertThat(found.get(0).evidence().lines().orElseThrow().start()).isEqualTo(7);
    }

    @Test
    void aKeySourceWithoutAlgorithmsUsesSpringsRs256Default() {
        Observation found = run("spring.security.oauth2.resourceserver.jwt.issuer-uri: https://idp\n".replace("spring.security.oauth2.resourceserver.jwt.issuer-uri: https://idp\n",
                "spring:\n  security:\n    oauth2:\n      resourceserver:\n        jwt:\n          issuer-uri: https://idp\n")).only();

        assertThat(found.algorithm().rawName()).isEqualTo("RS256");
        assertThat(found.confidence()).isEqualTo(0.6);
    }

    @Test
    void unrelatedConfigurationAndUnknownAlgorithmsReportNothing() {
        assertThat(run("server:\n  port: 1\n").observations()).isEmpty();
        DetectorHarness.Outcome unknown = run("spring:\n  security:\n    oauth2:\n      resourceserver:\n        jwt:\n          jws-algorithms: XX999\n");
        assertThat(unknown.observations()).isEmpty();
        assertThat(unknown.unresolved()).containsExactly("XX999");
    }
}

