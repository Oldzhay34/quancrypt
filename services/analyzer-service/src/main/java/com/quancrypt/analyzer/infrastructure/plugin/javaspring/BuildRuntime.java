package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import java.util.List;

/** Reads the Java and Spring Boot version of a project from its build files. */
public interface BuildRuntime {

    RuntimeInfo read(com.quancrypt.analyzer.port.outbound.SourceTree tree, List<ProjectFile> files);
}
