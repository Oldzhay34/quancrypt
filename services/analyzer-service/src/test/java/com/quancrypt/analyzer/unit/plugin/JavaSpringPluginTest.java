package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;
import com.quancrypt.analyzer.domain.model.AlgorithmFamily;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.AnalysisOutcome;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugin;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaCipherDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.BuildRuntimeReader;
import java.util.List;
import java.util.Optional;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.quancrypt.analyzer.infrastructure.redaction.PatternRedactor;
import com.quancrypt.analyzer.infrastructure.redaction.RedactionRules;
import org.junit.jupiter.api.Test;

class JavaSpringPluginTest {

    private final JavaSpringPlugin plugin = JavaSpringPlugins.standard(DetectorHarness.names());

    private static final String POM = """
            <project>
              <parent>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-parent</artifactId>
                <version>3.2.0</version>
              </parent>
              <properties><java.version>17</java.version></properties>
              <dependencies>
                <dependency><groupId>org.bouncycastle</groupId><artifactId>bcprov-jdk18on</artifactId><version>1.78</version></dependency>
              </dependencies>
            </project>
            """;

    private static String crypto(String className, String body) {
        return "import javax.crypto.Cipher;\nimport java.security.Signature;\nimport java.security.KeyPairGenerator;\n"
                + "import javax.crypto.KEM;\n\nclass " + className + " {\n    void run(String unknown) throws Exception {\n        " + body
                + "\n    }\n}\n";
    }

    private AnalysisOutcome analyze(String... pathsAndContents) {
        return plugin.analyze(DetectorHarness.tree(pathsAndContents));
    }

    @Test
    void findsWhatTheDetectorsSeeAndReturnsItInAStableOrder() {
        AnalysisOutcome outcome = analyze("pom.xml", POM,
                "src/main/java/B.java", crypto("B", "Cipher.getInstance(\"RSA/ECB/PKCS1Padding\"); Cipher.getInstance(\"DES\");"),
                "src/main/java/A.java", crypto("A", "Signature.getInstance(\"SHA256withRSA\");"));

        List<CryptoUsage> usages = outcome.usages();
        assertThat(usages).extracting(u -> u.evidence().file().value() + ":" + u.algorithm().family() + ":" + u.priority())
                .containsExactly("src/main/java/A.java:RSA:P2", "src/main/java/B.java:DES:P0", "src/main/java/B.java:RSA:P0");
        assertThat(analyze("pom.xml", POM, "src/main/java/A.java", crypto("A", "Signature.getInstance(\"SHA256withRSA\");"),
                "src/main/java/B.java", crypto("B", "Cipher.getInstance(\"RSA/ECB/PKCS1Padding\"); Cipher.getInstance(\"DES\");")).usages())
                .isEqualTo(usages);
    }

    @Test
    void testCodeIsKeptAndMarked() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/test/java/ATest.java", crypto("ATest", "Cipher.getInstance(\"DES\");"));

        assertThat(outcome.usages()).hasSize(1);
        assertThat(outcome.usages().get(0).evidence().locationKind()).isEqualTo(LocationKind.TEST_CODE);
        assertThat(outcome.usages().get(0).inTestCode()).isTrue();
    }

    @Test
    void generatedOutputAndToolDirectoriesAreNotAnalyzed() {
        String des = crypto("X", "Cipher.getInstance(\"DES\");");
        AnalysisOutcome outcome = analyze("pom.xml", POM, "target/generated/X.java", des, "node_modules/lib/X.java", des,
                ".git/hooks/X.java", des, "src/main/java/Real.java", des.replace("class X", "class Real"));

        assertThat(outcome.usages()).extracting(u -> u.evidence().file().value()).containsExactly("src/main/java/Real.java");
        assertThat(outcome.diagnostics().javaFilesParsed()).isEqualTo(1);
    }

    @Test
    void usagesThatNeedNoMigrationAreDropped() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Safe.java",
                crypto("Safe", "Cipher.getInstance(\"AES/GCM/NoPadding\"); KEM.getInstance(\"ML-KEM-768\"); Cipher.getInstance(\"ChaCha20-Poly1305\");"));

        assertThat(outcome.usages()).isEmpty();
    }

    @Test
    void usagesTheTableCannotPlaceCarryTheDetectorsPriorityOrTheMediumDefault() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Unknown.java", crypto("Unknown", "Cipher.getInstance(unknown);"),
                "src/main/java/Trust.java", """
                        import javax.net.ssl.X509TrustManager;

                        class Trust implements X509TrustManager {
                            public void checkClientTrusted(java.security.cert.X509Certificate[] c, String t) { }
                            public void checkServerTrusted(java.security.cert.X509Certificate[] c, String t) { }
                            public java.security.cert.X509Certificate[] getAcceptedIssuers() { return null; }
                        }
                        """);

        assertThat(outcome.usages()).extracting(u -> u.evidence().file().value() + ":" + u.priority())
                .containsExactly("src/main/java/Trust.java:P0", "src/main/java/Unknown.java:P2");
    }

    @Test
    void tlsAndCertificateUsagesWithAnUnknownAlgorithmTakeThePriorityOfTheirContext() {
        // No certificate file in the analysed root (a single QBank service, D-203): the key family stays UNKNOWN and the
        // priority comes from the context column, which is what core-service can plan (D-241).
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/resources/application.yml", """
                server:
                  ssl:
                    bundle: web
                    client-auth: need
                spring:
                  ssl:
                    bundle:
                      pem:
                        web:
                          keystore:
                            certificate: file:/certs/web.crt.pem
                            private-key: file:/certs/web.key.pem
                """);

        assertThat(outcome.usages()).isNotEmpty();
        assertThat(outcome.usages()).allSatisfy(u -> assertThat(u.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN));
        assertThat(outcome.usages()).extracting(u -> u.usageContext() + ":" + u.priority())
                .contains("TLS_KEY_EXCHANGE:P1", "MTLS_CLIENT_AUTH:P3", "CERTIFICATE:P3")
                .noneMatch(entry -> entry.endsWith(":P2"));
    }

    @Test
    void aGeneratedKeyIsReportedOnlyWhenNothingElseSaysWhatItIsFor() {
        AnalysisOutcome alone = analyze("pom.xml", POM, "src/main/java/Alone.java",
                crypto("Alone", "KeyPairGenerator.getInstance(\"RSA\").initialize(3072);"));
        AnalysisOutcome used = analyze("pom.xml", POM, "src/main/java/Used.java",
                crypto("Used", "KeyPairGenerator.getInstance(\"RSA\").initialize(3072); Cipher.getInstance(\"RSA/ECB/OAEPPadding\");"));

        assertThat(alone.usages()).hasSize(1);
        assertThat(alone.usages().get(0).usageContext()).isEqualTo(UsageContext.UNKNOWN);
        assertThat(alone.usages().get(0).priority()).isEqualTo(Priority.P2);
        assertThat(used.usages()).hasSize(1);
        assertThat(used.usages().get(0).usageContext()).isEqualTo(UsageContext.ENCRYPTION);
        assertThat(used.usages().get(0).algorithm().keySizeBits()).contains(3072);
    }

    @Test
    void aWeakGeneratedKeyIsAlwaysReported() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Weak.java",
                crypto("Weak", "KeyPairGenerator.getInstance(\"RSA\").initialize(1024); Cipher.getInstance(\"RSA/ECB/OAEPPadding\");"));

        assertThat(outcome.usages()).extracting(u -> u.usageContext() + ":" + u.priority()).containsExactlyInAnyOrder("UNKNOWN:P0", "ENCRYPTION:P0");
    }

    @Test
    void theSameFindingFromTwoDetectorsIsKeptOnceAtTheHigherConfidence() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Jwt.java", """
                import com.nimbusds.jose.JWSAlgorithm;

                class Jwt {
                    Object algorithm() {
                        String name = "RS256";
                        return JWSAlgorithm.RS256;
                    }
                }
                """);

        assertThat(outcome.usages()).hasSize(1);
        assertThat(outcome.usages().get(0).confidence()).isEqualTo(0.9);
        assertThat(outcome.usages().get(0).usageContext()).isEqualTo(UsageContext.TOKEN_SIGNATURE);
    }

    @Test
    void aDetectorThatFailsIsCountedAndTheOthersStillRun() {
        CryptoDetector failing = new CryptoDetector() {
            @Override
            public String detectorId() {
                return "test.failing";
            }

            @Override
            public boolean appliesTo(ProjectFile file) {
                return file.kind() == FileKind.JAVA;
            }

            @Override
            public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
                throw new IllegalStateException("boom");
            }
        };
        JavaSpringPlugin withFailure = JavaSpringPlugins.of(DetectorHarness.names(), List.of(failing, new JcaCipherDetector(DetectorHarness.names())),
                new BuildRuntimeReader());

        AnalysisOutcome outcome = withFailure.analyze(DetectorHarness.tree("pom.xml", POM, "src/main/java/A.java",
                crypto("A", "Cipher.getInstance(\"DES\");")));

        assertThat(outcome.usages()).hasSize(1);
        assertThat(outcome.diagnostics().detectorFailures()).containsExactly("test.failing on src/main/java/A.java: IllegalStateException");
    }

    @Test
    void javaThatCannotBeParsedIsCountedNotFatal() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Broken.java", "class { {{{ ((( ", "src/main/java/Fine.java",
                crypto("Fine", "Cipher.getInstance(\"DES\");"));

        assertThat(outcome.usages()).extracting(u -> u.evidence().file().value()).containsExactly("src/main/java/Fine.java");
        assertThat(outcome.diagnostics().javaFilesParsed() + outcome.diagnostics().javaFilesSkipped()).isEqualTo(2);
    }

    @Test
    void namesTheDictionaryDoesNotKnowAreListedInTheDiagnostics() {
        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Odd.java", crypto("Odd", "Cipher.getInstance(\"Blowfish\");"));

        assertThat(outcome.diagnostics().unresolvedNames()).containsExactly("jca.cipher: Blowfish");
    }

    @Test
    void cryptoLibrariesOfTheBuildFilesReachTheOutcome() {
        AnalysisOutcome outcome = analyze("pom.xml", POM);

        assertThat(outcome.libraries()).extracting(l -> l.artifact() + ":" + l.version().orElse("-")).containsExactly("bcprov-jdk18on:1.78");
    }

    @Test
    void theRuntimeVersionsComeFromTheBuildFile() {
        assertThat(plugin.runtimeInfo(DetectorHarness.tree("pom.xml", POM))).isEqualTo(new RuntimeInfo(Optional.of("17"), Optional.of("3.2.0")));
        assertThat(plugin.runtimeInfo(DetectorHarness.tree("src/main/java/A.java", "class A {}"))).isEqualTo(RuntimeInfo.UNKNOWN);
    }

    @Test
    void itSupportsMavenAndGradleAndSaysSoInItsInfo() {
        AnalysisRoot root = new AnalysisRoot(DetectorHarness.ROOT);

        assertThat(plugin.supports(new ProjectDescriptor(root, ProjectType.MAVEN))).isTrue();
        assertThat(plugin.supports(new ProjectDescriptor(root, ProjectType.GRADLE))).isTrue();
        assertThat(plugin.info().id()).isEqualTo("java-spring");
        assertThat(plugin.info().projectTypes()).containsExactlyInAnyOrder(ProjectType.MAVEN, ProjectType.GRADLE);
    }

    @Test
    void aProjectWithOneModuleIsOneNodeNamedAfterItsDirectoryAndHasNoEdges() {
        ServiceGraph graph = plugin.buildTopology(DetectorHarness.tree("pom.xml", POM));

        assertThat(graph.nodes()).extracting(n -> n.id()).containsExactly("project");
        assertThat(graph.edges()).isEmpty();
    }

    @Test
    void aProjectWithoutModulesOrComposeHasAnEmptyTopology() {
        assertThat(plugin.buildTopology(DetectorHarness.tree("src/main/java/A.java", "class A { }"))).isEqualTo(ServiceGraph.EMPTY);
    }

    @Test
    void aReadingLimitFailsTheAnalysisInsteadOfShrinkingItSilently() {
        var oneBigFile = new InMemorySourceTreeReader(100).file(DetectorHarness.ROOT, "pom.xml", "<project/>")
                .file(DetectorHarness.ROOT, "src/main/java/Big.java", "class Big {" + " ".repeat(200) + "}")
                .open(new AnalysisRoot(DetectorHarness.ROOT));
        var spentBudget = new InMemorySourceTreeReader().file(DetectorHarness.ROOT, "pom.xml", POM)
                .file(DetectorHarness.ROOT, "src/main/java/A.java", crypto("A", "Cipher.getInstance(\"DES\");"))
                .withTotalBudget(50).open(new AnalysisRoot(DetectorHarness.ROOT));

        assertThatThrownBy(() -> plugin.analyze(oneBigFile)).isInstanceOf(SourceTooLargeException.class);
        assertThatThrownBy(() -> plugin.analyze(spentBudget)).isInstanceOf(SourceTooLargeException.class);
    }

    @Test
    void anAbsurdlyDeepExpressionDoesNotStopTheAnalysis() {
        String deep = "class Deep { String s = " + "\"a\" + ".repeat(20_000) + "\"a\"; }";

        AnalysisOutcome outcome = analyze("pom.xml", POM, "src/main/java/Deep.java", deep, "src/main/java/Fine.java",
                crypto("Fine", "Cipher.getInstance(\"DES\");"));

        assertThat(outcome.usages()).extracting(u -> u.evidence().file().value()).containsExactly("src/main/java/Fine.java");
        assertThat(outcome.diagnostics().javaFilesParsed() + outcome.diagnostics().javaFilesSkipped()).isEqualTo(2);
    }

    @Test
    void aProjectWithMoreUsagesThanOneAnalysisCanHoldFailsAsTooLarge() {
        String[] files = new String[2 + 2 * 101];
        files[0] = "pom.xml";
        files[1] = POM;
        for (int i = 0; i < 101; i++) {
            files[2 + 2 * i] = "src/main/java/C" + i + ".java";
            files[3 + 2 * i] = crypto("C" + i, "Cipher.getInstance(\"DES\");".repeat(500));
        }

        assertThatThrownBy(() -> analyze(files)).isInstanceOf(SourceTooLargeException.class);
    }

    @Test
    void aProjectWithMoreConfigurationPropertiesThanOneAnalysisReadsFailsAsTooLarge() {
        String properties = java.util.stream.IntStream.range(0, 20_000).mapToObj(i -> "key" + i + "=v")
                .collect(java.util.stream.Collectors.joining("\n"));
        String[] files = new String[2 + 2 * 11];
        files[0] = "pom.xml";
        files[1] = POM;
        for (int i = 0; i < 11; i++) {
            files[2 + 2 * i] = "src/main/resources/application-p" + i + ".properties";
            files[3 + 2 * i] = properties;
        }

        assertThatThrownBy(() -> analyze(files)).isInstanceOf(SourceTooLargeException.class);
    }

    @Test
    void aSecretInALiteralNeverBecomesTheRawNameOfAnUnknownAlgorithmWhenASanitizerIsGiven() {
        PatternRedactor redactor = new PatternRedactor(RedactionRules.fromClasspath());
        JavaSpringPlugin sanitizing = JavaSpringPlugins.standard(DetectorHarness.names(),
                text -> redactor.redactLines(List.of(text)).get(0).equals(text) ? text : "unrecognized");

        AnalysisOutcome outcome = sanitizing.analyze(DetectorHarness.tree("pom.xml", POM, "src/main/java/A.java",
                crypto("A", "Cipher.getInstance(\"AKIAABCDEFGHIJKLMNOP\");")));

        assertThat(outcome.usages()).isNotEmpty().allSatisfy(u -> assertThat(u.algorithm().rawName()).doesNotContain("AKIA"));
        assertThat(outcome.usages()).extracting(u -> u.algorithm().rawName()).contains("unrecognized");
    }
}
