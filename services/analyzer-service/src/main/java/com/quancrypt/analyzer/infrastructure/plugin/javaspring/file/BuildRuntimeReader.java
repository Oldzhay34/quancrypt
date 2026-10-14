package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.BuildRuntime;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.nio.charset.StandardCharsets;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import javax.xml.stream.XMLStreamException;

/**
 * The Java and Spring Boot version of a project, from its build files. The build file nearest to the root that names a
 * version wins, so a module cannot override the root. A file that cannot be read or parsed says nothing.
 */
public final class BuildRuntimeReader implements BuildRuntime {

    @Override
    public RuntimeInfo read(SourceTree tree, List<ProjectFile> files) {
        List<ProjectFile> builds = files.stream().filter(f -> f.kind() == FileKind.POM || f.kind() == FileKind.GRADLE)
                .sorted(Comparator.comparingInt((ProjectFile f) -> f.path().segments().size()).thenComparing(f -> f.path().value())).toList();
        Optional<String> java = Optional.empty();
        Optional<String> boot = Optional.empty();
        for (ProjectFile build : builds) {
            BuildVersions versions = versions(tree, build);
            java = java.or(versions::java);
            boot = boot.or(versions::boot);
        }
        return new RuntimeInfo(java, boot);
    }

    private static BuildVersions versions(SourceTree tree, ProjectFile build) {
        try {
            if (build.kind() == FileKind.POM) {
                return MavenPom.parse(new String(tree.read(build.path()), StandardCharsets.UTF_8)).versions();
            }
            return GradleBuild.versions(tree.readLines(build.path()));
        } catch (XMLStreamException | SourceNotFoundException | PathNotAllowedException e) {
            return BuildVersions.none();
        }
    }
}
