package com.quancrypt.core.infrastructure.security;

import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import org.springframework.http.server.PathContainer;
import org.springframework.web.util.pattern.PathPattern;
import org.springframework.web.util.pattern.PathPatternParser;

/**
 * Which authentication schemes an operation accepts, as written in the `security` of contracts/openapi/core-service.yaml:
 * every operation accepts both the UI session token (bearerAuth) and the service token (internalToken), except the three
 * that change consents or delete a project (bearerAuth only) and the relay (internalToken only). A test compares this
 * table with the contract.
 */
public final class OperationPolicy {

    /** The credential schemes of the contract. */
    public enum Scheme {
        /** `Authorization: Bearer`, the UI session token; the caller kind UI. */
        BEARER,
        /** `X-Internal-Token`, the service token; the caller kind INTERNAL. */
        INTERNAL
    }

    private record Rule(String method, PathPattern pattern, Set<Scheme> schemes) {
    }

    private static final Set<Scheme> BOTH = Collections.unmodifiableSet(EnumSet.allOf(Scheme.class));
    private static final Set<Scheme> BEARER_ONLY = Collections.unmodifiableSet(EnumSet.of(Scheme.BEARER));
    private static final Set<Scheme> INTERNAL_ONLY = Collections.unmodifiableSet(EnumSet.of(Scheme.INTERNAL));

    private final List<Rule> rules;

    public OperationPolicy() {
        PathPatternParser parser = PathPatternParser.defaultInstance;
        rules = List.of(
                new Rule("DELETE", parser.parse("/api/v1/projects/{projectId}"), BEARER_ONLY),
                new Rule("POST", parser.parse("/api/v1/projects/{projectId}/consents"), BEARER_ONLY),
                new Rule("DELETE", parser.parse("/api/v1/projects/{projectId}/consents/{consentType}"), BEARER_ONLY),
                new Rule("POST", parser.parse("/api/v1/internal/outbox/relay"), INTERNAL_ONLY));
    }

    /** The schemes accepted for a request; an operation the table does not list accepts both (the contract default). */
    public Set<Scheme> accepted(String method, String path) {
        PathContainer container = PathContainer.parsePath(path);
        for (Rule rule : rules) {
            if (rule.method().equalsIgnoreCase(method) && rule.pattern().matches(container)) {
                return rule.schemes();
            }
        }
        return BOTH;
    }
}
