package com.quancrypt.analyzer.domain.model;

import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * The key exchange of a TLS edge as static analysis can say it (D-208). Nothing is negotiated here: when neither the code nor
 * the configuration names groups, the groups are what the project's Java version offers by default, so the value is
 * {@code inferred} and its confidence is below 1. The negotiated group is only measured by a handshake test (Phase 8).
 */
public record KeyExchange(GroupFamily groupFamily, List<String> groups, boolean inferred, double confidence) {

    private static final Pattern GROUP = Pattern.compile("[A-Za-z0-9_-]{1,32}");
    public static final int MAX_GROUPS = 20;

    public KeyExchange {
        Objects.requireNonNull(groupFamily, "groupFamily");
        groups = List.copyOf(groups);
        if (groups.size() > MAX_GROUPS || groups.stream().anyMatch(g -> !GROUP.matcher(g).matches())) {
            throw new IllegalArgumentException("groups are at most 20 names of 1 to 32 letters, digits, '_' or '-'");
        }
        if (!(confidence > 0.0 && confidence <= 1.0)) {
            throw new IllegalArgumentException("confidence must be above 0 and at most 1");
        }
        if (inferred && confidence >= 1.0) {
            throw new IllegalArgumentException("an inferred key exchange has a confidence below 1");
        }
    }
}
