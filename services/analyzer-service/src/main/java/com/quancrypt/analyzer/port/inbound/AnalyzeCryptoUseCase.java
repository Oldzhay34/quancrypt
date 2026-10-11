package com.quancrypt.analyzer.port.inbound;

/** Finds the crypto usages of a project and writes its CBOM. Failures are {@link AnalyzerUseCaseException}s. */
public interface AnalyzeCryptoUseCase {

    AnalysisView analyze(AnalyzeCryptoCommand command);
}
