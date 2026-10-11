package com.quancrypt.analyzer.port.inbound;

/** Reads redacted lines around a line of a file. Failures are {@link AnalyzerUseCaseException}s. */
public interface GetSnippetUseCase {

    SnippetView get(GetSnippetQuery query);
}
