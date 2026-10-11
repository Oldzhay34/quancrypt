package com.quancrypt.analyzer.port.inbound;

/** Finds the build system of a project. Failures are {@link AnalyzerUseCaseException}s. */
public interface DetectProjectTypeUseCase {

    ProjectView detect(DetectProjectTypeCommand command);
}
