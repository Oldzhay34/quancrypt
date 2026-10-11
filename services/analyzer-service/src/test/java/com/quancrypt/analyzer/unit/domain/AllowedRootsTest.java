package com.quancrypt.analyzer.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.model.AllowedRoots;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class AllowedRootsTest {

    @ParameterizedTest
    @ValueSource(strings = {"/workspace", "/workspace/qbank", "/corpus", "/corpus/p1/sub"})
    void rootsAtOrBelowTheAllowedDirectoriesAreAdmitted(String root) {
        assertThat(AllowedRoots.DEFAULT.admit(root).value()).isEqualTo(root);
    }

    @ParameterizedTest
    @ValueSource(strings = {"/workspaces", "/workspace2/x", "/corpusx", "/etc", "/", "/workspace/../etc", "/workspace/..",
        "/workspace/./x", "/workspace/", "/workspace//x", "workspace", "workspace/x", "/workspace/a\\b", "/workspace/a\u0000"})
    void otherRootsAreRefused(String root) {
        assertThatThrownBy(() -> AllowedRoots.DEFAULT.admit(root)).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void aMissingRootIsRefused() {
        assertThatThrownBy(() -> AllowedRoots.DEFAULT.admit(null)).isInstanceOf(PathNotAllowedException.class);
    }

    @Test
    void allowedDirectoriesMustBeCanonicalAndNotTheFileSystemRoot() {
        assertThatThrownBy(() -> new AllowedRoots(List.of("/"))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AllowedRoots(List.of("relative"))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AllowedRoots(List.of("/a/../b"))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AllowedRoots(List.of())).isInstanceOf(IllegalArgumentException.class);
    }
}
