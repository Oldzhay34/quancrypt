package com.quancrypt.analyzer.unit.usecase;

import static com.quancrypt.analyzer.unit.usecase.Fixtures.MAVEN_ROOT;
import static com.quancrypt.analyzer.unit.usecase.Fixtures.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.fake.FakePlugin;
import com.quancrypt.analyzer.fake.FixedIds;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.fake.RecordingCbomWriter;
import com.quancrypt.analyzer.fake.SteppingClock;
import com.quancrypt.analyzer.fake.Usages;
import com.quancrypt.analyzer.port.inbound.AnalysisView;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoCommand;
import com.quancrypt.analyzer.port.inbound.FindingView;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.usecase.AnalyzeCryptoService;
import com.quancrypt.analyzer.usecase.PluginSelector;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class AnalyzeCryptoServiceTest {

    private static final CryptoUsage MAIN = Usages.rsaEncryption("src/main/java/A.java", LocationKind.CODE);
    private static final CryptoUsage TEST = Usages.rsaEncryption("src/test/java/T.java", LocationKind.TEST_CODE);

    private final InMemorySourceTreeReader reader = Fixtures.projects();
    private final RecordingCbomWriter cbom = new RecordingCbomWriter();
    private final FakePlugin gradleOnly = new FakePlugin("gradle-only", ProjectType.GRADLE);
    private final FakePlugin java = new FakePlugin("java", ProjectType.MAVEN, ProjectType.GRADLE)
            .usages(List.of(MAIN, TEST))
            .runtime(new RuntimeInfo(Optional.of("25"), Optional.of("4.1.1")));
    private final FakePlugin later = new FakePlugin("later", ProjectType.MAVEN);

    private AnalyzeCryptoService service(FakePlugin... plugins) {
        return new AnalyzeCryptoService(Fixtures.opener(reader), new PluginSelector(List.of(plugins)), cbom, new FixedIds(),
                new SteppingClock(Instant.parse("2026-10-11T00:00:00Z"), Duration.ofMillis(250)));
    }

    @Test
    void theFirstPluginThatSupportsTheProjectAnalyzesIt() {
        AnalysisView result = service(gradleOnly, java, later).analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, true));

        assertThat(java.calls()).contains("analyzeCrypto", "runtimeInfo");
        assertThat(gradleOnly.calls()).containsExactly("supports");
        assertThat(later.calls()).isEmpty();
        assertThat(result.analysisId()).isEqualTo(FixedIds.ID);
        assertThat(result.projectType()).isEqualTo("MAVEN");
        assertThat(result.runtime().javaVersion()).contains("25");
        assertThat(result.runtime().springBootVersion()).contains("4.1.1");
        assertThat(result.cbom().specVersion()).isEqualTo("1.6");
        assertThat(result.stats().filesScanned()).isEqualTo(3);
        assertThat(result.stats().findingsTotal()).isEqualTo(2);
        assertThat(result.stats().durationMs()).isEqualTo(250);
    }

    @Test
    void testCodeFindingsAreKeptAndMarkedByDefaultAndDroppedOnRequest() {
        AnalysisView kept = service(java).analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, true));
        assertThat(kept.findings()).extracting(FindingView::locationKind).containsExactly("CODE", "TEST_CODE");

        AnalysisView dropped = service(java).analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, false));
        assertThat(dropped.findings()).extracting(FindingView::locationKind).containsExactly("CODE");
        assertThat(cbom.written()).containsExactly(MAIN);
        assertThat(dropped.stats().findingsTotal()).isEqualTo(1);
    }

    @Test
    void everyFindingFieldIsMappedToTheView() {
        java.usages(List.of(MAIN, Usages.certificateFile("certs/ca.crt.pem")));

        List<FindingView> findings = service(java).analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, true)).findings();

        assertThat(findings.get(0)).isEqualTo(new FindingView("src/main/java/A.java", Optional.of(10), Optional.of(12),
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding", "Card#encrypt", "RSA", Optional.of("ECB"),
                Optional.of("OAEPWithSHA-256AndMGF1Padding"), Optional.of("SHA-256"), Optional.of(2048), "ENCRYPTION", "CODE", "P1",
                Optional.of("JCA"), 0.9, "java.cipher"));
        assertThat(findings.get(1).lineStart()).isEmpty();
        assertThat(findings.get(1).lineEnd()).isEmpty();
        assertThat(findings.get(1).keySizeBits()).isEmpty();
        assertThat(findings.get(1).library()).isEmpty();
    }

    @Test
    void withoutASupportingPluginTheProjectIsUnsupported() {
        assertProblem(() -> service(gradleOnly).analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, true)), ProblemCode.UNSUPPORTED_PROJECT);
        assertProblem(() -> service().analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, true)), ProblemCode.UNSUPPORTED_PROJECT);
    }

    @Test
    void moreThanTheFindingLimitIsUnsupported() {
        java.usages(Collections.nCopies(AnalyzeCryptoService.MAX_FINDINGS + 1, MAIN));

        assertProblem(() -> service(java).analyze(new AnalyzeCryptoCommand(MAVEN_ROOT, true)), ProblemCode.UNSUPPORTED_PROJECT);
    }

    @Test
    void aRootOutsideTheAllowedDirectoriesIsRefusedBeforeAnyPluginRuns() {
        assertProblem(() -> service(java).analyze(new AnalyzeCryptoCommand("/home/user/project", true)), ProblemCode.PATH_NOT_ALLOWED);
        assertThat(java.calls()).isEmpty();
    }
}
