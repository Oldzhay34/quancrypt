package com.quancrypt.analyzer.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.AnalysisTimeoutException;
import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.policy.ProjectTypeDetector;
import com.quancrypt.analyzer.fake.FixedIds;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.fake.RecordingCbomWriter;
import com.quancrypt.analyzer.fake.SteppingClock;
import com.quancrypt.analyzer.infrastructure.filesystem.DeadlineSourceTreeReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoCommand;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.usecase.AnalyzeCryptoService;
import com.quancrypt.analyzer.usecase.PluginSelector;
import com.quancrypt.analyzer.usecase.ProjectOpener;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * The server side time budget (D-199): every listing and read of an opened tree checks the deadline, so a running analysis
 * stops at the next file with a timeout that the use case maps to its own problem code. The plugin must not swallow it.
 */
class DeadlineSourceTreeReaderTest {

    private static final String ROOT = "/workspace/p";
    private static final Instant START = Instant.parse("2026-10-14T12:00:00Z");

    private static CanonicalNames names() {
        return new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
    }

    private static InMemorySourceTreeReader project(int javaFiles) {
        InMemorySourceTreeReader reader = new InMemorySourceTreeReader().directory(ROOT).file(ROOT, "pom.xml", "<project/>");
        for (int i = 0; i < javaFiles; i++) {
            reader.file(ROOT, "src/main/java/C" + i + ".java", "class C" + i + " { }");
        }
        return reader;
    }

    @Test
    void aTreeAnswersWhileTheBudgetLasts() {
        SourceTree tree = new DeadlineSourceTreeReader(project(1), new SteppingClock(START, Duration.ofSeconds(1)), Duration.ofSeconds(100))
                .open(new AnalysisRoot(ROOT));

        assertThat(tree.files()).hasSize(2);
        assertThat(tree.exists(RelativePath.of("pom.xml"))).isTrue();
        assertThat(tree.readLines(RelativePath.of("pom.xml"))).containsExactly("<project/>");
        assertThat(tree.root().value()).isEqualTo(ROOT);
    }

    @Test
    void everyAccessFailsOnceTheBudgetIsSpent() {
        SourceTree tree = new DeadlineSourceTreeReader(project(1), new SteppingClock(START, Duration.ofSeconds(1)), Duration.ofSeconds(1))
                .open(new AnalysisRoot(ROOT));

        assertThatThrownBy(() -> {
            for (int i = 0; i < 5; i++) {
                tree.files();
            }
        }).isInstanceOf(AnalysisTimeoutException.class);
        assertThatThrownBy(() -> tree.exists(RelativePath.of("pom.xml"))).isInstanceOf(AnalysisTimeoutException.class);
        assertThatThrownBy(() -> tree.read(RelativePath.of("pom.xml"))).isInstanceOf(AnalysisTimeoutException.class);
        assertThatThrownBy(() -> tree.readLines(RelativePath.of("pom.xml"))).isInstanceOf(AnalysisTimeoutException.class)
                .hasMessage("the analysis ran past its time budget");
    }

    @Test
    void theBudgetStartsWhenATreeIsOpenedAndMustBePositive() {
        InMemorySourceTreeReader inner = project(1);
        SteppingClock clock = new SteppingClock(START, Duration.ofSeconds(1));

        assertThatThrownBy(() -> new DeadlineSourceTreeReader(inner, clock, Duration.ZERO)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new DeadlineSourceTreeReader(inner, clock, Duration.ofSeconds(-1))).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void aRunningAnalysisStopsWithTheTimeoutProblemAndThePluginDoesNotSwallowIt() {
        DeadlineSourceTreeReader reader = new DeadlineSourceTreeReader(project(40), new SteppingClock(START, Duration.ofSeconds(1)),
                Duration.ofSeconds(8));
        AnalyzeCryptoService service = new AnalyzeCryptoService(
                new ProjectOpener(new AllowedRoots(List.of("/workspace")), reader, new ProjectTypeDetector()),
                new PluginSelector(List.of(JavaSpringPlugins.standard(names()))), new RecordingCbomWriter(), new FixedIds(),
                new SteppingClock(START, Duration.ofMillis(1)));

        assertThatThrownBy(() -> service.analyze(new AnalyzeCryptoCommand(ROOT, true)))
                .isInstanceOfSatisfying(AnalyzerUseCaseException.class, e -> assertThat(e.problemCode()).isEqualTo(ProblemCode.ANALYSIS_TIMEOUT));
    }

    @Test
    void anAnalysisWithinTheBudgetCompletes() {
        DeadlineSourceTreeReader reader = new DeadlineSourceTreeReader(project(3), new SteppingClock(START, Duration.ofMillis(1)),
                Duration.ofSeconds(300));
        AnalyzeCryptoService service = new AnalyzeCryptoService(
                new ProjectOpener(new AllowedRoots(List.of("/workspace")), reader, new ProjectTypeDetector()),
                new PluginSelector(List.of(JavaSpringPlugins.standard(names()))), new RecordingCbomWriter(), new FixedIds(),
                new SteppingClock(START, Duration.ofMillis(1)));

        assertThat(service.analyze(new AnalyzeCryptoCommand(ROOT, true)).stats().filesScanned()).isEqualTo(4);
    }
}
