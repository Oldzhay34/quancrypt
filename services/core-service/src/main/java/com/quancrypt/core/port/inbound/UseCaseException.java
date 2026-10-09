package com.quancrypt.core.port.inbound;

/** A use case failed in a way the caller can act on; the api layer maps the problem code to an HTTP status. */
public final class UseCaseException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final ProblemCode problem;

    public UseCaseException(ProblemCode problem, String detail) {
        super(detail);
        this.problem = problem;
    }

    public ProblemCode problem() {
        return problem;
    }
}
