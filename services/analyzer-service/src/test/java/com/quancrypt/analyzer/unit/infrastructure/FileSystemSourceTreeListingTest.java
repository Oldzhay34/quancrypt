package com.quancrypt.analyzer.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * A tree lists its files once (D-205): the analysis asks three times and a slow disk makes every walk minutes. Reading
 * many files of one directory goes on working (the symbolic link refusals are covered by the reader contract tests).
 */
class FileSystemSourceTreeListingTest {

    @TempDir
    Path project;

    private SourceTree open() throws IOException {
        return new FileSystemSourceTreeReader().open(new AnalysisRoot(project.toRealPath().toString()));
    }

    @Test
    void theListIsTakenOnceAndANewTreeSeesNewFiles() throws IOException {
        Files.writeString(project.resolve("a.txt"), "a");
        SourceTree tree = open();

        List<RelativePath> first = tree.files();
        Files.writeString(project.resolve("b.txt"), "b");

        assertThat(tree.files()).isSameAs(first).extracting(RelativePath::value).containsExactly("a.txt");
        assertThat(open().files()).extracting(RelativePath::value).containsExactly("a.txt", "b.txt");
    }

    @Test
    void manyFilesOfOneDirectoryAreReadAndTheDirectoryIsCheckedOnlyOnce() throws IOException {
        Files.createDirectories(project.resolve("src/main"));
        for (int i = 0; i < 50; i++) {
            Files.writeString(project.resolve("src/main/F" + i + ".txt"), "line " + i + "\n");
        }
        SourceTree tree = open();

        for (int i = 0; i < 50; i++) {
            assertThat(tree.readLines(RelativePath.of("src/main/F" + i + ".txt"))).containsExactly("line " + i);
        }
        assertThat(tree.exists(RelativePath.of("src/main/F7.txt"))).isTrue();
    }
}
