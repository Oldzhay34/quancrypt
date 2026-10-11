package com.quancrypt.analyzer.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.UnsupportedProjectException;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.policy.ProjectTypeDetector;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ProjectTypeDetectorTest {

    private final ProjectTypeDetector detector = new ProjectTypeDetector();

    @Test
    void pomMeansMaven() {
        assertThat(detector.detect(Set.of("pom.xml")::contains)).isEqualTo(ProjectType.MAVEN);
    }

    @ParameterizedTest
    @ValueSource(strings = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"})
    void anyGradleBuildFileMeansGradle(String name) {
        assertThat(detector.detect(Set.of(name)::contains)).isEqualTo(ProjectType.GRADLE);
    }

    @Test
    void bothBuildSystemsCannotBeAnalyzed() {
        assertThatThrownBy(() -> detector.detect(Set.of("pom.xml", "build.gradle.kts")::contains))
                .isInstanceOf(UnsupportedProjectException.class);
    }

    @Test
    void noBuildFileCannotBeAnalyzed() {
        assertThatThrownBy(() -> detector.detect(Set.of("package.json")::contains)).isInstanceOf(UnsupportedProjectException.class);
    }
}
