package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaSignatureDetector;
import java.util.List;
import org.junit.jupiter.api.Test;

class JcaSignatureDetectorTest {

    private final JcaSignatureDetector detector = new JcaSignatureDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String call) {
        return DetectorHarness.run(detector, "src/main/java/Sign.java", """
                import java.security.Signature;

                class Sign {
                    static final String ALGORITHM = "SHA1withRSA";

                    void sign() throws Exception {
                        %s
                    }
                }
                """.replace("%s", call));
    }

    @Test
    void sha256WithRsaIsOneRsaSignature() {
        Observation found = run("Signature.getInstance(\"SHA256withRSA\");").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.algorithm().hash()).contains("SHA-256");
        assertThat(found.algorithm().padding()).contains("PKCS1_V1_5");
        assertThat(found.usage()).isEqualTo(UsageContext.SIGNATURE);
        assertThat(found.symbol()).isEqualTo("Sign#sign");
        assertThat(found.detectorId()).isEqualTo("jca.signature");
    }

    @Test
    void aBrokenHashIsAlsoReportedForTheHashFamily() {
        List<Observation> found = run("Signature.getInstance(ALGORITHM);").observations();

        assertThat(found).extracting(o -> o.algorithm().family()).containsExactly(AlgorithmFamily.RSA, AlgorithmFamily.SHA1);
        assertThat(found).extracting(Observation::usage).containsOnly(UsageContext.SIGNATURE);
        assertThat(found.get(1).algorithm().hash()).contains("SHA-1");
    }

    @Test
    void md5IsTheMd5Family() {
        List<Observation> found = run("Signature.getInstance(\"MD5withRSA\");").observations();

        assertThat(found).extracting(o -> o.algorithm().family()).containsExactly(AlgorithmFamily.RSA, AlgorithmFamily.MD5);
    }

    @Test
    void ecdsaAndEdDsaAreFoundByTheirNames() {
        assertThat(run("Signature.getInstance(\"SHA256withECDSA\");").only().algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(run("Signature.getInstance(\"Ed25519\");").only().algorithm().family()).isEqualTo(AlgorithmFamily.EDDSA);
    }

    @Test
    void unresolvedAndUnknownNamesAreUnknownFamilyButStillSignatures() {
        Observation unresolved = run("Signature.getInstance(System.getenv(\"A\"));").only();
        DetectorHarness.Outcome unknown = run("Signature.getInstance(\"SHA7withNothing\");");

        assertThat(unresolved.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(unresolved.usage()).isEqualTo(UsageContext.SIGNATURE);
        assertThat(unknown.unresolved()).containsExactly("SHA7withNothing");
    }
}

