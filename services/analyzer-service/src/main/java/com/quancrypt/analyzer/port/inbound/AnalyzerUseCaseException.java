package com.quancrypt.analyzer.port.inbound;

import java.util.Objects;

/** A use case failure with its contract problem code; the detail is a fixed sentence without the caller's input. */
public final class AnalyzerUseCaseException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final ProblemCode problemCode;

    public AnalyzerUseCaseException(ProblemCode problemCode, String detail) {
        super(detail);
        this.problemCode = Objects.requireNonNull(problemCode, "problemCode");
    }

    public ProblemCode problemCode() {
        return problemCode;
    }
}
