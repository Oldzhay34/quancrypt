package com.quancrypt.core.port.inbound;

/** Problem codes of RFC 9457 error responses (problem type: https://quancrypt.local/problems/code). */
public enum ProblemCode {
    VALIDATION_FAILED("validation-failed"),
    UNAUTHORIZED("unauthorized"),
    FORBIDDEN("forbidden"),
    NOT_FOUND("not-found"),
    SCAN_ALREADY_RUNNING("scan-already-running"),
    SCAN_NOT_RUNNING("scan-not-running"),
    SCAN_NOT_COMPLETED("scan-not-completed"),
    FINDING_LIMIT_EXCEEDED("finding-limit-exceeded"),
    PLAN_ALREADY_EXISTS("plan-already-exists"),
    INVALID_STATE_TRANSITION("invalid-state-transition"),
    CONCURRENT_MODIFICATION("concurrent-modification"),
    IDEMPOTENCY_CONFLICT("idempotency-conflict"),
    PRECONDITION_REQUIRED("precondition-required"),
    PAYLOAD_TOO_LARGE("payload-too-large"),
    UNSUPPORTED_MEDIA_TYPE("unsupported-media-type"),
    INTERNAL_ERROR("internal-error");

    private final String code;

    ProblemCode(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
