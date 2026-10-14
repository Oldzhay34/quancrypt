package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKeyPairGeneratorDetector;
import org.junit.jupiter.api.Test;

class JcaKeyPairGeneratorDetectorTest {

    private final JcaKeyPairGeneratorDetector detector = new JcaKeyPairGeneratorDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String body) {
        return DetectorHarness.run(detector, "src/main/java/Gen.java", """
                import java.security.KeyPairGenerator;
                import java.security.spec.ECGenParameterSpec;
                import java.security.spec.RSAKeyGenParameterSpec;

                class Gen {
                    static final int BITS = 3072;

                    void generate() throws Exception {
                        %s
                    }
                }
                """.replace("%s", body));
    }

    @Test
    void aStrongRsaKeyIsAFallbackWithItsSize() {
        Observation found = run("KeyPairGenerator g = KeyPairGenerator.getInstance(\"RSA\"); g.initialize(2048);").only();

        assertThat(found.role()).isEqualTo(Role.FALLBACK);
        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.algorithm().keySizeBits()).contains(2048);
        assertThat(found.usage()).isEqualTo(UsageContext.UNKNOWN);
    }

    @Test
    void aWeakRsaKeyIsAFindingBecauseTheKeyItselfIsTheProblem() {
        Observation found = run("KeyPairGenerator g = KeyPairGenerator.getInstance(\"RSA\"); g.initialize(1024);").only();

        assertThat(found.role()).isEqualTo(Role.FINDING);
        assertThat(found.algorithm().keySizeBits()).contains(1024);
    }

    @Test
    void sizesFromConstantsAndSpecsAreRead() {
        assertThat(run("KeyPairGenerator.getInstance(\"RSA\").initialize(BITS);").only().algorithm().keySizeBits()).contains(3072);
        assertThat(run("KeyPairGenerator.getInstance(\"RSA\").initialize(new RSAKeyGenParameterSpec(4096, RSAKeyGenParameterSpec.F4));").only()
                .algorithm().keySizeBits()).contains(4096);
        Observation ec = run("KeyPairGenerator.getInstance(\"EC\").initialize(new ECGenParameterSpec(\"secp256r1\"));").only();
        assertThat(ec.algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(ec.algorithm().keySizeBits()).contains(256);
    }

    @Test
    void withoutAnInitializeCallTheSizeStaysEmpty() {
        assertThat(run("KeyPairGenerator.getInstance(\"RSA\");").only().algorithm().keySizeBits()).isEmpty();
    }

    @Test
    void anUnknownAlgorithmNameIsOnlyNoted() {
        DetectorHarness.Outcome outcome = run("KeyPairGenerator.getInstance(\"Nothing\");");

        assertThat(outcome.observations()).isEmpty();
        assertThat(outcome.unresolved()).containsExactly("Nothing");
    }
}

