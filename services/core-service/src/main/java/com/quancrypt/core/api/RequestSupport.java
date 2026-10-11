package com.quancrypt.core.api;

import com.quancrypt.core.facade.error.ApiProblemException;
import com.quancrypt.core.facade.error.ProblemKind;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.security.core.Authentication;

/** Small helpers every controller shares: the caller kind of the authenticated request and the If-Match header. */
public final class RequestSupport {

    static final String INTERNAL_AUTHORITY = "ROLE_INTERNAL";
    private static final Pattern IF_MATCH = Pattern.compile("^\"([0-9]{1,9})\"$");

    private RequestSupport() {
    }

    /** UI for the session token, INTERNAL for the service token (set by the security filter). */
    public static String caller(Authentication authentication) {
        boolean internal = authentication.getAuthorities().stream().anyMatch(a -> INTERNAL_AUTHORITY.equals(a.getAuthority()));
        return internal ? "INTERNAL" : "UI";
    }

    public static Optional<String> key(String idempotencyKey) {
        return Optional.ofNullable(idempotencyKey);
    }

    /**
     * The version of a required If-Match header: a missing or unusable header is 428 (the contract of these operations has
     * no 400 for it; TransitionPlanItem and RevokeConsent declare 428 for "a valid If-Match is required").
     */
    public static int requiredVersion(String ifMatch) {
        if (ifMatch == null || !IF_MATCH.matcher(ifMatch).matches()) {
            throw new ApiProblemException(ProblemKind.PRECONDITION_REQUIRED,
                    "the If-Match header with the version of the resource in quotes, for example \"3\", is required");
        }
        return parse(ifMatch);
    }

    public static Optional<Integer> optionalVersion(String ifMatch) {
        return ifMatch == null ? Optional.empty() : Optional.of(parse(ifMatch));
    }

    private static int parse(String ifMatch) {
        Matcher m = IF_MATCH.matcher(ifMatch);
        if (!m.matches()) {
            throw new ApiProblemException(ProblemKind.VALIDATION_FAILED, "If-Match must be the version in quotes, for example \"3\"");
        }
        return Integer.parseInt(m.group(1));
    }
}
