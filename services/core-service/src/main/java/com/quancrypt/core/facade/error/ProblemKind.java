package com.quancrypt.core.facade.error;

/** The problem types of the contract (RFC 9457 `type` is https://quancrypt.local/problems/CODE) with their HTTP status. */
public enum ProblemKind {
    VALIDATION_FAILED(400, "validation-failed", "Validation failed"),
    UNAUTHORIZED(401, "unauthorized", "Unauthorized"),
    FORBIDDEN(403, "forbidden", "Forbidden"),
    NOT_FOUND(404, "not-found", "Not found"),
    SCAN_ALREADY_RUNNING(409, "scan-already-running", "Scan already running"),
    SCAN_NOT_RUNNING(409, "scan-not-running", "Scan not running"),
    SCAN_NOT_COMPLETED(409, "scan-not-completed", "Scan not completed"),
    FINDING_LIMIT_EXCEEDED(409, "finding-limit-exceeded", "Finding limit exceeded"),
    PLAN_ALREADY_EXISTS(409, "plan-already-exists", "Plan already exists"),
    INVALID_STATE_TRANSITION(409, "invalid-state-transition", "Invalid state transition"),
    CONCURRENT_MODIFICATION(409, "concurrent-modification", "Concurrent modification"),
    IDEMPOTENCY_CONFLICT(409, "idempotency-conflict", "Idempotency conflict"),
    PRECONDITION_REQUIRED(428, "precondition-required", "Precondition required"),
    PAYLOAD_TOO_LARGE(413, "payload-too-large", "Payload too large"),
    UNSUPPORTED_MEDIA_TYPE(415, "unsupported-media-type", "Unsupported media type"),
    INTERNAL_ERROR(500, "internal-error", "Internal error");

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
