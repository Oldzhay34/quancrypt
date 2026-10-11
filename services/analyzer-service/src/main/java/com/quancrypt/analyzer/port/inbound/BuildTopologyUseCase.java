package com.quancrypt.analyzer.port.inbound;

/** Builds the service topology of a project. Failures are {@link AnalyzerUseCaseException}s. */
public interface BuildTopologyUseCase {

    TopologyView build(BuildTopologyCommand command);
}
