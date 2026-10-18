package com.quancrypt.analyzer.unit.usecase;

import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import static com.quancrypt.analyzer.unit.usecase.Fixtures.MAVEN_ROOT;
import static com.quancrypt.analyzer.unit.usecase.Fixtures.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.policy.SensitiveFilePolicy;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.fake.MarkingRedactor;
import com.quancrypt.analyzer.port.inbound.GetSnippetQuery;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.inbound.SnippetLineView;
import com.quancrypt.analyzer.port.inbound.SnippetView;
import com.quancrypt.analyzer.usecase.GetSnippetService;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class GetSnippetServiceTest {

    private static final String FILE = "src/main/java/A.java";

    private final InMemorySourceTreeReader reader = Fixtures.projects()
            .file(MAVEN_ROOT, FILE, IntStream.rangeClosed(1, 30).mapToObj(i -> "line " + i + (i == 15 ? " secret" : ""))
                    .collect(Collectors.joining("\r\n", "", "\r\n")));
    private final MarkingRedactor redactor = new MarkingRedactor();
    private final GetSnippetService service = new GetSnippetService(AllowedRoots.DEFAULT, reader, redactor, new SensitiveFilePolicy());

    @Test
    void returnsTheLineAndItsContextRedacted() {
        SnippetView view = service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 15, 2));

        assertThat(view.path()).isEqualTo(FILE);
        assertThat(view.lines()).containsExactly(new SnippetLineView(13, "line 13"), new SnippetLineView(14, "line 14"),
                new SnippetLineView(15, "line 15 [REDACTED]"), new SnippetLineView(16, "line 16"), new SnippetLineView(17, "line 17"));
        assertThat(redactor.seen()).hasSize(30);
    }

    @Test
    void theWindowIsClippedAtTheEndsOfTheFile() {
        assertThat(service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 1, 10)).lines()).extracting(SnippetLineView::number)
                .containsExactlyElementsOf(IntStream.rangeClosed(1, 11).boxed().toList());
        assertThat(service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 30, 10)).lines()).extracting(SnippetLineView::number)
                .containsExactlyElementsOf(IntStream.rangeClosed(20, 30).boxed().toList());
        assertThat(service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 7, 0)).lines()).containsExactly(new SnippetLineView(7, "line 7"));
    }

    @Test
    void contextAndLineOutsideTheirRangesAreInvalid() {
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 5, 11)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 5, -1)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 0, 3)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, null, 1, 3)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aLineAfterTheEndOrAMissingFileIsNotFound() {
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 31, 3)), ProblemCode.NOT_FOUND);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "src/main/java/Missing.java", 1, 3)), ProblemCode.NOT_FOUND);
    }

    @Test
    void aRootInsideTheQuancryptStateDirectoryIsRefused() {
        assertThatThrownBy(() -> service.get(new GetSnippetQuery("/workspace/.quancrypt", "session.token", 1, 0)))
                .isInstanceOf(AnalyzerUseCaseException.class);
    }

    @Test
    void pathsThatLeaveTheRootAreRefused() {
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "../gradle/build.gradle.kts", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "src/../../gradle/build.gradle.kts", 1, 0)),
                ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "/etc/passwd", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.get(new GetSnippetQuery("/etc", "passwd", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
    }

    @Test
    void symbolicLinksAreRefused() {
        reader.file(MAVEN_ROOT, "link.txt", "x").link(MAVEN_ROOT, "link.txt")
                .file(MAVEN_ROOT, "linkdir/inner.txt", "x").link(MAVEN_ROOT, "linkdir");

        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "link.txt", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "linkdir/inner.txt", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
    }

    @Test
    void longLinesAreCutAfterRedaction() {
        reader.file(MAVEN_ROOT, "long.txt", "x".repeat(GetSnippetService.MAX_LINE_LENGTH + 50));

        assertThat(service.get(new GetSnippetQuery(MAVEN_ROOT, "long.txt", 1, 0)).lines().get(0).text())
                .hasSize(GetSnippetService.MAX_LINE_LENGTH);
    }

    @Test
    void aFileOverTheReadingLimitIsAnUnsupportedProject() {
        InMemorySourceTreeReader small = new InMemorySourceTreeReader(8).file(MAVEN_ROOT, "big.txt", "0123456789");
        GetSnippetService limited = new GetSnippetService(AllowedRoots.DEFAULT, small, redactor, new SensitiveFilePolicy());

        assertProblem(() -> limited.get(new GetSnippetQuery(MAVEN_ROOT, "big.txt", 1, 0)), ProblemCode.UNSUPPORTED_PROJECT);
    }

    @Test
    void problemDetailsNeverRepeatTheInput() {
        assertThatThrownBy(() -> service.get(new GetSnippetQuery("/etc/hidden-root", "x", 1, 0))).hasMessageNotContaining("hidden-root");
        assertThatThrownBy(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "../hidden-file", 1, 0))).hasMessageNotContaining("hidden-file");
        assertThatThrownBy(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "hidden-missing.txt", 1, 0)))
                .hasMessageNotContaining("hidden-missing");
    }

    @Test
    void aWindowStartingInsideAPrivateKeyIsMaskedBecauseTheWholeFileIsRedacted() {
        reader.file(MAVEN_ROOT, "keys.txt", String.join("\n", "intro", "-----BEGIN PRIVATE KEY-----",
                "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj",
                "MzEfYyjiWA4R4/M2bS1GB4t7NXp98C3SC6dVMvDuictGeurT8jNbvJZHtCSuYEvu", "aZpKRKtZ5hbh1w==",
                "-----END PRIVATE KEY-----", "outro"));

        SnippetView view = service.get(new GetSnippetQuery(MAVEN_ROOT, "keys.txt", 4, 1));

        assertThat(view.lines()).extracting(SnippetLineView::text).containsOnly(MarkingRedactor.KEY_MASK);
        assertThat(service.get(new GetSnippetQuery(MAVEN_ROOT, "keys.txt", 7, 0)).lines().get(0).text()).isEqualTo("outro");
    }

    @Test
    void secretBearingFilesAreNeverServed() {
        reader.file(MAVEN_ROOT, ".env", "DB_PASSWORD=x").file(MAVEN_ROOT, "certs/server.p12", "binary")
                .file(MAVEN_ROOT, "certs/out/ca.key.pem", "-----BEGIN PRIVATE KEY-----");

        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, ".env", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "certs/server.p12", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.get(new GetSnippetQuery(MAVEN_ROOT, "certs/out/ca.key.pem", 1, 0)), ProblemCode.PATH_NOT_ALLOWED);
    }

    @Test
    void aRedactorThatChangesTheLineCountIsADefect() {
        GetSnippetService broken = new GetSnippetService(AllowedRoots.DEFAULT, reader, lines -> lines.subList(0, 1),
                new SensitiveFilePolicy());

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> broken.get(new GetSnippetQuery(MAVEN_ROOT, FILE, 2, 0)))
                .isInstanceOf(IllegalStateException.class);
    }
}
