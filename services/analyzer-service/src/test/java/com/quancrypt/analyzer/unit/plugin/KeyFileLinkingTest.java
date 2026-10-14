package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.AnalysisOutcome;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugin;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class KeyFileLinkingTest {

    private final JavaSpringPlugin plugin = JavaSpringPlugins.standard(DetectorHarness.names());

    private static final String POM = "<project><properties><java.version>25</java.version></properties></project>";

    private static final String SIGNER = """
            import java.nio.file.Path;
            import java.security.Signature;

            final class TokenSigner {
                static TokenSigner fromFiles(Path publicKey, Path privateKey) {
                    return new TokenSigner();
                }

                byte[] sign() throws Exception {
                    return Signature.getInstance("SHA256withRSA").sign();
                }
            }
            """;

    private static final String WIRING = """
            import java.nio.file.Path;

            class Wiring {
                static final String NAME = "app-signing";

                Object signer(Path dir) {
                    return TokenSigner.fromFiles(dir.resolve(NAME + ".pub.pem"), dir.resolve(NAME + ".key.pem"));
                }
            }
            """;

    private Map<String, CryptoUsage> byFile(AnalysisOutcome outcome, String... exclude) {
        return outcome.usages().stream().filter(u -> u.evidence().file().value().startsWith("certs/"))
                .collect(Collectors.toMap(u -> u.evidence().file().value(), u -> u, (a, b) -> a));
    }

    @Test
    void aKeyPairTakesItsUsageFromTheClassItIsHandedTo() {
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM, "src/main/java/TokenSigner.java", SIGNER,
                "src/main/java/Wiring.java", WIRING, "certs/app-signing.pub.pem", TestPems.RSA_2048_PUBLIC_KEY,
                "certs/app-signing.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER));

        Map<String, CryptoUsage> keys = byFile(outcome);
        assertThat(keys.get("certs/app-signing.pub.pem").usageContext()).isEqualTo(UsageContext.SIGNATURE);
        assertThat(keys.get("certs/app-signing.key.pem").usageContext()).isEqualTo(UsageContext.SIGNATURE);
        assertThat(keys.get("certs/app-signing.key.pem").algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(keys.get("certs/app-signing.key.pem").algorithm().keySizeBits()).contains(2048);
        assertThat(keys.get("certs/app-signing.pub.pem").priority()).isEqualTo(Priority.P2);
        assertThat(keys.get("certs/app-signing.pub.pem").confidence()).isEqualTo(0.6);
    }

    @Test
    void theClassThatUsesAKeyLearnsItsSize() {
        String weakPem = TestPems.RSA_1024_SHA1_CERTIFICATE;
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM, "src/main/java/TokenSigner.java", SIGNER,
                "src/main/java/Wiring.java", WIRING, "certs/app-signing.pub.pem", TestPems.RSA_2048_PUBLIC_KEY,
                "certs/other.crt.pem", weakPem));

        CryptoUsage signer = outcome.usages().stream().filter(u -> u.evidence().file().value().equals("src/main/java/TokenSigner.java")).findFirst()
                .orElseThrow();
        assertThat(signer.algorithm().keySizeBits()).contains(2048);
    }

    @Test
    void aHolderClassIsFollowedToTheClassesThatTakeIt() {
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM,
                "src/main/java/KeyHolder.java", """
                        import java.nio.file.Path;

                        final class KeyHolder {
                            static KeyHolder load(Path file) {
                                return new KeyHolder();
                            }
                        }
                        """,
                "src/main/java/Encryptor.java", """
                        import javax.crypto.Cipher;

                        final class Encryptor {
                            Encryptor(KeyHolder holder) throws Exception {
                                Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
                            }
                        }
                        """,
                "src/main/java/Wiring.java", """
                        import java.nio.file.Path;

                        class Wiring {
                            Object holder(Path dir) {
                                return KeyHolder.load(dir.resolve("holder.pub.pem"));
                            }
                        }
                        """, "certs/holder.pub.pem", TestPems.RSA_2048_PUBLIC_KEY));

        assertThat(byFile(outcome).get("certs/holder.pub.pem").usageContext()).isEqualTo(UsageContext.ENCRYPTION);
    }

    @Test
    void whenTheClassesDisagreeTheUsageStaysUnknown() {
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM,
                "src/main/java/KeyHolder.java", "import java.nio.file.Path;\nfinal class KeyHolder {\n    static KeyHolder load(Path file) {\n        return null;\n    }\n}\n",
                "src/main/java/Encryptor.java", "import javax.crypto.Cipher;\nfinal class Encryptor {\n    Encryptor(KeyHolder h) throws Exception {\n        Cipher.getInstance(\"RSA/ECB/OAEPPadding\");\n    }\n}\n",
                "src/main/java/Signer.java", "import java.security.Signature;\nfinal class Signer {\n    Signer(KeyHolder h) throws Exception {\n        Signature.getInstance(\"SHA256withRSA\");\n    }\n}\n",
                "src/main/java/Wiring.java", "import java.nio.file.Path;\nclass Wiring {\n    Object holder(Path dir) {\n        return KeyHolder.load(dir.resolve(\"tie.pub.pem\"));\n    }\n}\n",
                "certs/tie.pub.pem", TestPems.RSA_2048_PUBLIC_KEY));

        CryptoUsage key = byFile(outcome).get("certs/tie.pub.pem");
        assertThat(key.usageContext()).isEqualTo(UsageContext.UNKNOWN);
        assertThat(key.confidence()).isEqualTo(0.3);
        assertThat(key.priority()).isEqualTo(Priority.P2);
    }

    @Test
    void testCodeDoesNotDecideWhatAKeyIsUsedFor() {
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM, "src/main/java/TokenSigner.java", SIGNER,
                "src/main/java/Wiring.java", WIRING, "certs/app-signing.pub.pem", TestPems.RSA_2048_PUBLIC_KEY,
                "src/test/java/TokenSignerTest.java", "import javax.crypto.Cipher;\nclass TokenSignerTest {\n    TokenSignerTest(TokenSigner s) throws Exception {\n"
                        + "        Cipher.getInstance(\"RSA/ECB/OAEPPadding\");\n    }\n}\n"));

        assertThat(byFile(outcome).get("certs/app-signing.pub.pem").usageContext()).isEqualTo(UsageContext.SIGNATURE);
    }

    @Test
    void aKeyNothingReferencesIsUnknownAndOneNextToItsCertificateBelongsToIt() {
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM, "certs/lonely.pub.pem", TestPems.RSA_2048_PUBLIC_KEY,
                "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/server.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER));

        Map<String, CryptoUsage> keys = byFile(outcome);
        assertThat(keys.get("certs/lonely.pub.pem").usageContext()).isEqualTo(UsageContext.UNKNOWN);
        assertThat(keys.get("certs/server.key.pem").usageContext()).isEqualTo(UsageContext.CERTIFICATE);
        assertThat(keys.get("certs/server.key.pem").priority()).isEqualTo(Priority.P3);
    }

    @Test
    void theHalfOfAPairTheCodeNeverLoadsTakesTheOthersUsage() {
        AnalysisOutcome outcome = plugin.analyze(DetectorHarness.tree("pom.xml", POM, "src/main/java/TokenSigner.java", SIGNER,
                "src/main/java/Wiring.java", WIRING.replace("dir.resolve(NAME + \".key.pem\")", "null"), "certs/app-signing.pub.pem",
                TestPems.RSA_2048_PUBLIC_KEY, "certs/app-signing.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER));

        assertThat(byFile(outcome).get("certs/app-signing.key.pem").usageContext()).isEqualTo(UsageContext.SIGNATURE);
    }
}

