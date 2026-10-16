package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** Paths of compose files (build contexts, bind mounts) are resolved inside the analyzed root and never outside it. */
class ProjectPathsTest {

    @Test
    void relativePathsAreResolvedAgainstTheDirectoryOfTheFile() {
        assertThat(ProjectPaths.resolve("deploy", "./a/b")).isEqualTo(Optional.of("deploy/a/b"));
        assertThat(ProjectPaths.resolve("deploy/x", "../y/z")).isEqualTo(Optional.of("deploy/y/z"));
        assertThat(ProjectPaths.resolve("", ".")).isEqualTo(Optional.of(""));
    }

    @ParameterizedTest
    @ValueSource(strings = {"/etc/passwd", "../outside", "a/../../outside", "~/secrets", "C:/x", "c:\\x", "dir\\file", "$HOME/x", ""})
    void anAbsolutePathOrOneThatLeavesTheRootIsRefused(String path) {
        assertThat(ProjectPaths.resolve("", path)).isEmpty();
    }

    @Test
    void aTextBecomesANodeIdTheContractAccepts() {
        assertThat(ProjectPaths.nodeId("host:8443/ü x")).matches("[A-Za-z0-9._-]{1,200}");
        assertThat(ProjectPaths.nodeId("a".repeat(500))).hasSize(200);
        assertThat(ProjectPaths.nodeId("")).isEqualTo("unnamed");
    }

    @Test
    void directoryAndBaseNameSplitAtTheLastSlash() {
        assertThat(ProjectPaths.directoryOf("a/b/c.txt")).isEqualTo("a/b");
        assertThat(ProjectPaths.directoryOf("c.txt")).isEmpty();
        assertThat(ProjectPaths.baseName("a/b/c.txt")).isEqualTo("c.txt");
    }
}
