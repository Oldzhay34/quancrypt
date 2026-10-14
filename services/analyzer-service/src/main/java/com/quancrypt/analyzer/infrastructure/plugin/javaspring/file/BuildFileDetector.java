package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.LibraryDependency;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import java.nio.charset.StandardCharsets;
import java.util.List;
import javax.xml.stream.XMLStreamException;

/**
 * Maven and Gradle build files: the crypto libraries the project depends on, with their versions (facts for the CBOM). The
 * detector never reports a finding by itself, because a dependency is not a usage. The Java and Spring Boot versions are read
 * by {@link BuildRuntimeReader}.
 */
public final class BuildFileDetector implements CryptoDetector {

    public static final String ID = "build.file";

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public boolean appliesTo(ProjectFile file) {
        return file.kind() == FileKind.POM || file.kind() == FileKind.GRADLE;
    }

    @Override
    public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
        ProjectFile file = context.file();
        List<BuildDependency> dependencies = file.kind() == FileKind.POM ? pom(index, file) : GradleBuild.dependencies(index.lines(file.path()));
        for (BuildDependency dependency : dependencies) {
            if (CryptoLibraries.isCrypto(dependency.group(), dependency.artifact())) {
                sink.library(new LibraryDependency(file.path(), dependency.group(), dependency.artifact(),
                        dependency.version().flatMap(v -> BuildVersions.valid(v, false)), dependency.line()));
            }
        }
    }

    private static List<BuildDependency> pom(ProjectIndex index, ProjectFile file) {
        try {
            return MavenPom.parse(new String(index.tree().read(file.path()), StandardCharsets.UTF_8)).dependencies();
        } catch (XMLStreamException | SourceNotFoundException | PathNotAllowedException e) {
            return List.of();
        }
    }
}
