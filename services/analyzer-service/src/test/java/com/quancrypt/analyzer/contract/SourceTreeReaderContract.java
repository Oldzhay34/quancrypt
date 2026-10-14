package com.quancrypt.analyzer.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * The contract every SourceTreeReader keeps (LSP, solid-checklist): the in-memory test double and the file system adapter
 * pass the same tests. Path safety: symbolic links (to files or directories, outside or inside the root) are never
 * followed or listed, a root that is a link is refused, and files over the reading limit are refused.
 */
public abstract class SourceTreeReaderContract {

    /** The reading limit every fixture's reader is built with. */
    protected static final long LIMIT = 64;

    /** A project directory a contract test builds up, plus things outside it. */
    protected interface Fixture {

        SourceTreeReader reader();

        AnalysisRoot root();

        void file(String path, byte[] content);

        /** A symbolic link at {@code path} to a file outside the root containing "outside". */
        void linkToOutsideFile(String path);

        /** A symbolic link at {@code path} to a directory outside the root holding "secret.txt". */
        void linkToOutsideDirectory(String path);

        /** A symbolic link at {@code path} to the file {@code target} inside the root. */
        void linkInside(String path, String target);

        /** A root that is itself a symbolic link to a real project directory. */
        AnalysisRoot linkedRoot();

        /** A root path where nothing exists. */
        AnalysisRoot missingRoot();

        /** A reader that hands out at most {@code bytes} bytes per opened tree, over the same project. */
        SourceTreeReader readerWithTotalBudget(long bytes);
    }

    private Fixture fixture;

    protected abstract Fixture newFixture();

    @BeforeEach
    void setUp() {
        fixture = newFixture();
        fixture.file("pom.xml", bytes("<project/>"));
        fixture.file("src/main/java/A.java", bytes("class A {\r\n  int x;\r\n}\r\n"));
        fixture.file("src/main/resources/application.yml", bytes("server:\n  port: 1"));
    }

    private SourceTree tree() {
        return fixture.reader().open(fixture.root());
    }

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    @Test
    void readsARegularFileByItsRelativePath() {
        SourceTree tree = tree();

        assertThat(tree.root()).isEqualTo(fixture.root());
        assertThat(tree.read(RelativePath.of("pom.xml"))).isEqualTo(bytes("<project/>"));
        assertThat(tree.readLines(RelativePath.of("src/main/java/A.java"))).containsExactly("class A {", "  int x;", "}");
        assertThat(tree.readLines(RelativePath.of("src/main/resources/application.yml"))).containsExactly("server:", "  port: 1");
        assertThat(tree.exists(RelativePath.of("pom.xml"))).isTrue();
        assertThat(tree.exists(RelativePath.of("build.gradle"))).isFalse();
    }

    @Test
    void listsRegularFilesSortedAndSlashSeparated() {
        assertThat(tree().files()).extracting(RelativePath::value)
                .containsExactly("pom.xml", "src/main/java/A.java", "src/main/resources/application.yml");
    }

    @Test
    void aLinkToAFileOutsideTheRootIsNeitherListedNorRead() {
        fixture.linkToOutsideFile("leak.txt");
        SourceTree tree = tree();

        assertThat(tree.files()).extracting(RelativePath::value).doesNotContain("leak.txt");
        assertThatThrownBy(() -> tree.read(RelativePath.of("leak.txt"))).isInstanceOf(PathNotAllowedException.class);
        assertThatThrownBy(() -> tree.readLines(RelativePath.of("leak.txt"))).isInstanceOf(PathNotAllowedException.class);
        assertThatThrownBy(() -> tree.exists(RelativePath.of("leak.txt"))).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void aPathThroughALinkedDirectoryIsRefused() {
        fixture.linkToOutsideDirectory("src/linked");
        SourceTree tree = tree();

        assertThat(tree.files()).extracting(RelativePath::value).noneMatch(path -> path.startsWith("src/linked"));
        assertThatThrownBy(() -> tree.read(RelativePath.of("src/linked/secret.txt"))).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void aLinkIsRefusedEvenWhenItPointsInsideTheRoot() {
        fixture.linkInside("alias.xml", "pom.xml");
        SourceTree tree = tree();

        assertThat(tree.files()).extracting(RelativePath::value).doesNotContain("alias.xml");
        assertThatThrownBy(() -> tree.read(RelativePath.of("alias.xml"))).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void aMissingFileOrADirectoryIsNotFound() {
        SourceTree tree = tree();

        assertThatThrownBy(() -> tree.read(RelativePath.of("missing.txt"))).isInstanceOf(SourceNotFoundException.class);
        assertThatThrownBy(() -> tree.read(RelativePath.of("src/main"))).isInstanceOf(SourceNotFoundException.class);
        assertThat(tree.exists(RelativePath.of("src/main"))).isFalse();
    }

    @Test
    void aFileOverTheReadingLimitIsRefused() {
        fixture.file("big.bin", new byte[(int) LIMIT + 1]);
        fixture.file("edge.bin", new byte[(int) LIMIT]);
        SourceTree tree = tree();

        assertThat(tree.read(RelativePath.of("edge.bin"))).hasSize((int) LIMIT);
        assertThatThrownBy(() -> tree.read(RelativePath.of("big.bin"))).isInstanceOf(SourceTooLargeException.class);
    }

    @Test
    void aTreeStopsHandingOutBytesWhenItsTotalBudgetIsSpent() {
        fixture.file("a.bin", new byte[60]);
        fixture.file("b.bin", new byte[60]);
        SourceTree tree = fixture.readerWithTotalBudget(100).open(fixture.root());

        tree.read(RelativePath.of("a.bin"));
        assertThatThrownBy(() -> tree.read(RelativePath.of("b.bin"))).isInstanceOf(SourceTooLargeException.class);
    }

    @Test
    void aRootThatIsALinkOrDoesNotExistIsRefused() {
        assertThatThrownBy(() -> fixture.reader().open(fixture.linkedRoot())).isInstanceOf(PathNotAllowedException.class);
        assertThatThrownBy(() -> fixture.reader().open(fixture.missingRoot())).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void anEmptyFileHasNoLines() {
        fixture.file("empty.txt", new byte[0]);

        assertThat(tree().readLines(RelativePath.of("empty.txt"))).isEmpty();
    }
}
