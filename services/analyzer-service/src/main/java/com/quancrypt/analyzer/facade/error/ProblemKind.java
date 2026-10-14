package com.quancrypt.analyzer.facade.error;

/** The problem types of the contract (RFC 9457 `type` is https://quancrypt.local/problems/CODE) with their HTTP status. */
public enum ProblemKind {
    VALIDATION_FAILED(400, "validation-failed", "Validation failed"),
    PATH_NOT_ALLOWED(400, "path-not-allowed", "Path not allowed"),
    UNAUTHORIZED(401, "unauthorized", "Unauthorized"),
    NOT_FOUND(404, "not-found", "Not found"),
    UNSUPPORTED_PROJECT(422, "unsupported-project", "Unsupported project"),
    INTERNAL_ERROR(500, "internal-error", "Internal error"),
    ANALYSIS_TIMEOUT(504, "analysis-timeout", "Analysis timeout");

    public static final String TYPE_BASE = "https://quancrypt.local/problems/";

    private final int status;
    private final String code;
    private final String title;

    ProblemKind(int status, String code, String title) {
        this.status = status;
        this.code = code;
        this.title = title;
    }

    public int status() {
        return status;
    }

    public String code() {
        return code;
    }

    public String title() {
        return title;
    }

    public String type() {
        return TYPE_BASE + code;
    }
}
