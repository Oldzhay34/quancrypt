package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaCipherDetector;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class JcaCipherDetectorTest {

    private final JcaCipherDetector detector = new JcaCipherDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String body) {
        return DetectorHarness.run(detector, "src/main/java/Demo.java", """
                import javax.crypto.Cipher;

                public class Demo {
                    static final String ALGORITHM = "AES/" + "CBC/PKCS5Padding";

                    void encrypt() throws Exception {
                        %s
                    }
                }
                """.replace("%s", body));
    }

    @Test
    void rsaOaepIsRsaWithModeNoneAndOaepPaddingAndTheHash() {
        Observation found = run("Cipher c = Cipher.getInstance(\"RSA/ECB/OAEPWithSHA-256AndMGF1Padding\");").only();

        CryptoAlgorithm algorithm = found.algorithm();
        assertThat(algorithm.family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(algorithm.mode()).contains("NONE");
        assertThat(algorithm.padding()).contains("OAEP");
        assertThat(algorithm.hash()).contains("SHA-256");
        assertThat(found.usage()).isEqualTo(UsageContext.ENCRYPTION);
        assertThat(found.confidence()).isEqualTo(0.9);
        assertThat(found.symbol()).isEqualTo("Demo#encrypt");
        assertThat(found.detectorId()).isEqualTo("jca.cipher");
        assertThat(found.library()).contains("JCA");
        assertThat(found.role()).isEqualTo(Role.FINDING);
        assertThat(found.evidence().locationKind()).isEqualTo(LocationKind.CODE);
        assertThat(found.evidence().lines().orElseThrow().start()).isEqualTo(7);
    }

    @Test
    void rsaPkcs1PaddingIsNamedAsSuch() {
        CryptoAlgorithm algorithm = run("Cipher.getInstance(\"RSA/ECB/PKCS1Padding\");").only().algorithm();

        assertThat(algorithm.mode()).contains("NONE");
        assertThat(algorithm.padding()).contains("PKCS1_V1_5");
    }

    @Test
    void aeadModesAreSymmetricEncryption() {
        Observation found = run("Cipher.getInstance(\"AES/GCM/NoPadding\");").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.AES);
        assertThat(found.algorithm().mode()).contains("GCM");
        assertThat(found.usage()).isEqualTo(UsageContext.SYMMETRIC_ENCRYPTION);
    }

    @Test
    void aBlockCipherWithoutAModeRunsInEcbAtALowerConfidence() {
        Observation found = run("Cipher.getInstance(\"AES\");").only();

        assertThat(found.algorithm().mode()).contains("ECB");
        assertThat(found.confidence()).isEqualTo(0.7);
    }

    @Test
    void tripleDesAndDesAreTheirOwnFamilies() {
        assertThat(run("Cipher.getInstance(\"DESede/CBC/PKCS5Padding\");").only().algorithm().family()).isEqualTo(AlgorithmFamily.TRIPLE_DES);
        assertThat(run("Cipher.getInstance(\"DES/ECB/PKCS5Padding\");").only().algorithm().family()).isEqualTo(AlgorithmFamily.DES);
    }

    @Test
    void aConstantOfTheSameUnitIsResolved() {
        Observation found = run("Cipher.getInstance(ALGORITHM);").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.AES);
        assertThat(found.algorithm().mode()).contains("CBC");
        assertThat(found.algorithm().rawName()).isEqualTo("AES/CBC/PKCS5Padding");
    }

    @Test
    void aValueThatCannotBeResolvedIsUnknownAtLowConfidence() {
        Observation found = run("Cipher.getInstance(System.getProperty(\"alg\"));").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(found.usage()).isEqualTo(UsageContext.UNKNOWN);
        assertThat(found.confidence()).isEqualTo(0.3);
    }

    @Test
    void aNameTheDictionaryDoesNotKnowIsReportedAsUnresolvedAndAsUnknown() {
        DetectorHarness.Outcome outcome = run("Cipher.getInstance(\"Blowfish/CBC/PKCS5Padding\");");

        assertThat(outcome.only().algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(outcome.unresolved()).containsExactly("Blowfish/CBC/PKCS5Padding");
    }

    @Test
    void wrapModeInTheSameMethodMakesItKeyWrapping() {
        Observation found = run("Cipher c = Cipher.getInstance(\"RSA/ECB/OAEPPadding\"); c.init(Cipher.WRAP_MODE, (java.security.Key) null);").only();

        assertThat(found.usage()).isEqualTo(UsageContext.KEY_WRAP);
    }

    @Test
    void aCipherClassThatIsNotTheJdksIsIgnored() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/java/Other.java", """
                import com.acme.Cipher;

                class Other {
                    void run() {
                        Cipher.getInstance("RSA");
                    }
                }
                """);

        assertThat(outcome.observations()).isEmpty();
    }

    @Test
    void aFullyQualifiedCallWithoutAnImportIsFound() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/java/Q.java", """
                class Q {
                    void run() throws Exception {
                        javax.crypto.Cipher.getInstance("AES/CBC/PKCS5Padding");
                    }
                }
                """);

        assertThat(outcome.only().algorithm().family()).isEqualTo(AlgorithmFamily.AES);
    }

    @Test
    void testCodeIsMarkedNotDropped() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/test/java/DemoTest.java", """
                import javax.crypto.Cipher;

                class DemoTest {
                    void run() throws Exception {
                        Cipher.getInstance("DES");
                    }
                }
                """);

        assertThat(outcome.only().evidence().locationKind()).isEqualTo(LocationKind.TEST_CODE);
    }

    @Test
    void nothingIsReportedForFilesThatAreNotJava() {
        assertThat(DetectorHarness.run(detector, "notes.txt", "Cipher.getInstance(\"AES\")").observations()).isEmpty();
    }

    @Test
    void anUnknownNameThatDoesNotLookLikeAnAlgorithmIsNotCopiedIntoTheFinding() {
        DetectorHarness.Outcome outcome = run("Cipher.getInstance(\"my own secret value!\");");

        assertThat(outcome.only().algorithm().rawName()).isEqualTo("unrecognized");
        assertThat(outcome.only().algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
    }

    @Test
    void aConstantOfAnotherTypeIsNotMistakenForOneOfThisUnit() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "src/main/java/Demo.java", """
                import javax.crypto.Cipher;

                public class Demo {
                    static final String ALGORITHM = "DES";

                    void encrypt() throws Exception {
                        Cipher.getInstance(Other.ALGORITHM);
                        Cipher.getInstance(Demo.ALGORITHM);
                        Cipher.getInstance(this.ALGORITHM);
                    }
                }
                """);

        assertThat(outcome.observations()).extracting(o -> o.algorithm().family())
                .containsExactlyInAnyOrder(AlgorithmFamily.UNKNOWN, AlgorithmFamily.DES, AlgorithmFamily.DES);
    }

    @Test
    void aGeneratedConstantLongerThanAnyNameIsNotResolvedAndNotBuiltForEveryUse() {
        String big = "A".repeat(2_000);
        String source = "import javax.crypto.Cipher;\npublic class Demo {\n    static final String K = \"" + big + "\";\n"
                + "    static final String B = K + (K + (K + (K + K)));\n    void f() throws Exception {\n"
                + "        Cipher.getInstance(B);\n".repeat(500) + "    }\n}\n";

        DetectorHarness.Outcome outcome = assertTimeoutPreemptively(Duration.ofSeconds(10),
                () -> DetectorHarness.run(detector, "src/main/java/Demo.java", source));

        assertThat(outcome.observations()).hasSize(500);
        assertThat(outcome.observations()).allSatisfy(o -> assertThat(o.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN));
    }

    @Test
    void aNameWithInvisibleCharactersStillFindsItsRowAndDoesNotStopTheFile() {
        DetectorHarness.Outcome outcome = run("Cipher.getInstance(\"DES\\t\"); Cipher.getInstance(\"AES/ECB/PKCS5Padding\");");

        assertThat(outcome.observations()).extracting(o -> o.algorithm().family()).containsExactly(AlgorithmFamily.DES, AlgorithmFamily.AES);
        assertThat(outcome.observations().get(0).algorithm().rawName()).isEqualTo("DES");
    }
}
