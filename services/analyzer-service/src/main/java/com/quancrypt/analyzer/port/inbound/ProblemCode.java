package com.quancrypt.analyzer.port.inbound;

/** The problem codes of the analyzer contract that a use case can raise (RFC 9457 type suffix). */
public enum ProblemCode {
    VALIDATION_FAILED("validation-failed"),
    PATH_NOT_ALLOWED("path-not-allowed"),
    NOT_FOUND("not-found"),
    UNSUPPORTED_PROJECT("unsupported-project");

    private final String code;

    ProblemCode(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
