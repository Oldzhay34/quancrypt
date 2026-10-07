package com.quancrypt.qbank.account.api.error;

import org.springframework.http.HttpStatusCode;

/** Problem type code, title and fixed detail for an HTTP status. */
record ProblemKind(String code, String title, String detail) {

    static final String TYPE_BASE = "https://quancrypt.local/problems/";

    private static final ProblemKind VALIDATION =
            new ProblemKind("validation-failed", "Validation failed", "The request is malformed or fails validation.");
    private static final ProblemKind UNAUTHORIZED =
            new ProblemKind("unauthorized", "Unauthorized", "Missing, invalid or expired credentials.");
    private static final ProblemKind FORBIDDEN =
            new ProblemKind("forbidden", "Forbidden", "The caller is not allowed to access this resource.");
    private static final ProblemKind NOT_FOUND =
            new ProblemKind("not-found", "Not found", "The resource does not exist.");
    private static final ProblemKind METHOD_NOT_ALLOWED =
            new ProblemKind("method-not-allowed", "Method not allowed", "The HTTP method is not supported.");
    private static final ProblemKind UNSUPPORTED_MEDIA_TYPE =
            new ProblemKind("unsupported-media-type", "Unsupported media type", "The media type is not supported.");
    private static final ProblemKind INTERNAL =
            new ProblemKind("internal-error", "Internal error", "The service failed to process the request.");

    static ProblemKind of(HttpStatusCode status) {
        return switch (status.value()) {
            case 400 -> VALIDATION;
            case 401 -> UNAUTHORIZED;
            case 403 -> FORBIDDEN;
            case 404 -> NOT_FOUND;
            case 405 -> METHOD_NOT_ALLOWED;
            case 415 -> UNSUPPORTED_MEDIA_TYPE;
            default -> status.is4xxClientError() ? VALIDATION : INTERNAL;
        };
    }
}
