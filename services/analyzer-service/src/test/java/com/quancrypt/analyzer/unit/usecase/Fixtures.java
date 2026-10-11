package com.quancrypt.analyzer.unit.usecase;

import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.policy.ProjectTypeDetector;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.usecase.ProjectOpener;
import org.assertj.core.api.ThrowableAssert.ThrowingCallable;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Shared set-up of the use case tests. */
final class Fixtures {

    static final String MAVEN_ROOT = "/workspace/maven";
    static final String GRADLE_ROOT = "/workspace/gradle";

    private Fixtures() {
    }

    static InMemorySourceTreeReader projects() {
        return new InMemorySourceTreeReader()
                .file(MAVEN_ROOT, "pom.xml", "<project/>")
                .file(MAVEN_ROOT, "src/main/java/A.java", "class A {}")
                .file(MAVEN_ROOT, "src/test/java/T.java", "class T {}")
                .file(GRADLE_ROOT, "build.gradle.kts", "plugins {}");
    }

    static ProjectOpener opener(InMemorySourceTreeReader reader) {
        return new ProjectOpener(AllowedRoots.DEFAULT, reader, new ProjectTypeDetector());
    }

    static void assertProblem(ThrowingCallable call, ProblemCode code) {
        assertThatThrownBy(call).isInstanceOfSatisfying(AnalyzerUseCaseException.class,
                e -> org.assertj.core.api.Assertions.assertThat(e.problemCode()).isEqualTo(code));
    }
}
