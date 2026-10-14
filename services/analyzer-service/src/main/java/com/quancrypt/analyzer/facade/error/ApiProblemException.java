package com.quancrypt.analyzer.facade.error;

/** A failure the api layer renders as a problem+json response; the detail is a fixed or use case supplied sentence. */
public final class ApiProblemException extends RuntimeException {

    private static final long serialVersionUID = 1L;
    private static final int MAX_DETAIL = 300;

    private final ProblemKind kind;

    public ApiProblemException(ProblemKind kind, String detail) {
        super(detail == null ? kind.title() : detail.substring(0, Math.min(detail.length(), MAX_DETAIL)));
        this.kind = kind;
    }

    public ProblemKind kind() {
        return kind;
    }
}
