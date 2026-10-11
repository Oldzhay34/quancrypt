package com.quancrypt.analyzer.domain.policy;

import com.quancrypt.analyzer.domain.exception.UnsupportedProjectException;
import com.quancrypt.analyzer.domain.model.ProjectType;
import java.util.List;
import java.util.function.Predicate;

/**
 * Decides the build system from the build files at the project root (D-178h): pom.xml means Maven, build.gradle(.kts)
 * or settings.gradle(.kts) means Gradle; both or neither cannot be analyzed.
 */
public final class ProjectTypeDetector {

    public static final List<String> MAVEN_FILES = List.of("pom.xml");
    public static final List<String> GRADLE_FILES = List.of("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts");

    /** The project type, given which top-level file names exist at the root. */
    public ProjectType detect(Predicate<String> existsAtRoot) {
        boolean maven = MAVEN_FILES.stream().anyMatch(existsAtRoot);
        boolean gradle = GRADLE_FILES.stream().anyMatch(existsAtRoot);
        if (maven && gradle) {
            throw new UnsupportedProjectException("the root has both Maven and Gradle build files");
        }
        if (maven) {
            return ProjectType.MAVEN;
        }
        if (gradle) {
            return ProjectType.GRADLE;
        }
        throw new UnsupportedProjectException("the root has no Maven or Gradle build file");
    }
}
