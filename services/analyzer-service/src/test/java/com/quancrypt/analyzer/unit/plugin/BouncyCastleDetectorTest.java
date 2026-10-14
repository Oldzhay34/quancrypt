package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.BouncyCastleDetector;
import java.util.List;
import org.junit.jupiter.api.Test;

class BouncyCastleDetectorTest {

    private final BouncyCastleDetector detector = new BouncyCastleDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String body) {
        return DetectorHarness.run(detector, "src/main/java/Bc.java", """
                import org.bouncycastle.crypto.*;

                class Bc {
                    void run() throws Exception {
                        %s
                    }
                }
                """.replace("%s", body).replace("org.bouncycastle.crypto.*", "org.bouncycastle.crypto.engines.RSAEngine"));
    }

    @Test
    void lightweightRsaClassesAreFoundWithTheirPadding() {
        List<Observation> found = run("new PKCS1Encoding(new RSAEngine()); new OAEPEncoding(new RSAEngine());").observations();

        assertThat(found).extracting(o -> o.algorithm().rawName()).containsExactlyInAnyOrder("PKCS1Encoding", "OAEPEncoding", "RSAEngine",
                "RSAEngine");
        assertThat(found).extracting(o -> o.algorithm().padding().orElse("-")).contains("PKCS1_V1_5", "OAEP");
        assertThat(found).extracting(o -> o.algorithm().family()).containsOnly(AlgorithmFamily.RSA);
        assertThat(found).extracting(Observation::usage).containsOnly(UsageContext.ENCRYPTION);
        assertThat(found.get(0).library()).contains("BouncyCastle");
    }

    @Test
    void signersAgreementsAndOldCiphersAreFound() {
        List<Observation> found = run("new RSADigestSigner(null); new ECDSASigner(); new X25519Agreement(); new DESEngine();").observations();

        assertThat(found).extracting(o -> o.algorithm().family()).containsExactlyInAnyOrder(AlgorithmFamily.RSA, AlgorithmFamily.ECDSA,
                AlgorithmFamily.X25519, AlgorithmFamily.DES);
    }

    @Test
    void aSignerBuilderWithABrokenHashIsAlsoReportedForTheHash() {
        List<Observation> found = run("new JcaContentSignerBuilder(\"SHA1withRSA\");").observations();

        assertThat(found).extracting(o -> o.algorithm().family()).containsExactly(AlgorithmFamily.RSA, AlgorithmFamily.SHA1);
        assertThat(found).extracting(Observation::usage).containsOnly(UsageContext.SIGNATURE);
    }

    @Test
    void keyGenerationParametersGiveTheSize() {
        Observation weak = run("new RSAKeyGenerationParameters(null, null, 1024, 80);").only();
        Observation strong = run("new RSAKeyGenerationParameters(null, null, 2048, 80);").only();

        assertThat(weak.role()).isEqualTo(Role.FINDING);
        assertThat(weak.algorithm().keySizeBits()).contains(1024);
        assertThat(strong.role()).isEqualTo(Role.FALLBACK);
    }

    @Test
    void filesThatDoNotImportBouncyCastleAreIgnored() {
        assertThat(DetectorHarness.run(detector, "src/main/java/Plain.java", """
                class Plain {
                    Object run() {
                        return new RSAEngine();
                    }
                }
                """).observations()).isEmpty();
    }
}

