package com.quancrypt.analyzer.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** File system specifics beyond the shared contract. */
class FileSystemSourceTreeReaderTest {

    @TempDir
    Path temp;

    @Test
    void aRootBelowALinkedParentIsRefused() throws IOException {
        Path real = Files.createDirectories(temp.toRealPath().resolve("real/project"));
        Files.writeString(real.resolve("pom.xml"), "<project/>");
        Path linkedParent = Files.createSymbolicLink(temp.toRealPath().resolve("alias"), real.getParent());

        assertThatThrownBy(() -> new FileSystemSourceTreeReader().open(new AnalysisRoot(linkedParent.resolve("project").toString())))
                .isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void aRegularFileAsRootIsRefused() throws IOException {
        Path file = Files.writeString(temp.toRealPath().resolve("file.txt"), "x");

        assertThatThrownBy(() -> new FileSystemSourceTreeReader().open(new AnalysisRoot(file.toString())))
                .isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void moreFilesThanTheLimitAreRefused() throws IOException {
        Path root = temp.toRealPath();
        for (int i = 0; i < 4; i++) {
            Files.writeString(root.resolve("f" + i + ".txt"), "x");
        }

        assertThatThrownBy(() -> new FileSystemSourceTreeReader(1024, 3).open(new AnalysisRoot(root.toString())).files())
                .isInstanceOf(SourceTooLargeException.class);
    }

    @Test
    void malformedUtf8IsReplacedNotRejected() throws IOException {
        Path root = temp.toRealPath();
        Files.write(root.resolve("bad.txt"), new byte[] {'a', (byte) 0xff, 'b', '\n'});

        assertThat(new FileSystemSourceTreeReader().open(new AnalysisRoot(root.toString())).readLines(RelativePath.of("bad.txt")))
                .containsExactly("a\uFFFDb");
        assertThat("a\uFFFDb".getBytes(StandardCharsets.UTF_8)).hasSize(5);
    }

    @Test
    void theLimitsMustBePositive() {
        assertThatThrownBy(() -> new FileSystemSourceTreeReader(0, 1)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new FileSystemSourceTreeReader(1, 0)).isInstanceOf(IllegalArgumentException.class);
    }
}
