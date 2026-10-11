package com.quancrypt.analyzer.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.model.RelativePath;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.api.Test;

class RelativePathTest {

    @Test
    void aPlainRelativePathIsKeptAsIs() {
        RelativePath path = RelativePath.of("src/main/java/A.java");

        assertThat(path.value()).isEqualTo("src/main/java/A.java");
        assertThat(path.segments()).containsExactly("src", "main", "java", "A.java");
    }

    @Test
    void dotsInsideANameAreNotSegments() {
        assertThat(RelativePath.of("a..b/.hidden/x..").segments()).containsExactly("a..b", ".hidden", "x..");
    }

    @ParameterizedTest
    @ValueSource(strings = {"..", "../x", "a/..", "a/../b", "a/../../etc/passwd", ".", "./a", "a/./b", "/etc/passwd", "/",
        "C:/Windows", "c:x", "a\\b", "..\\x", "", "a//b", "a/", "a\u0000b", "a\nb", "a\u007fb", "a\u0085b",
        "evil‮txt.java", "a​b", "a b", "a﻿b"})
    void unsafePathsAreRefused(String value) {
        assertThatThrownBy(() -> RelativePath.of(value)).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void tooLongPathsAreRefused() {
        assertThatThrownBy(() -> RelativePath.of("a".repeat(1025))).isInstanceOf(PathNotAllowedException.class);
        assertThat(RelativePath.of("a".repeat(1024)).value()).hasSize(1024);
    }

    @Test
    void theRefusalNeverRepeatsTheInput() {
        assertThatThrownBy(() -> RelativePath.of("../secret-name")).hasMessageNotContaining("secret-name");
    }
}
