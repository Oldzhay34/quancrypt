package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.port.outbound.TokenIssuer;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/** Test double: records every call and returns a predictable token. */
public final class FakeTokenIssuer implements TokenIssuer {

    /** One recorded call. */
    public record Call(String subject, Instant issuedAt, Duration lifetime) {
    }

    private final List<Call> calls = new ArrayList<>();

    @Override
    public String issue(String subject, Instant issuedAt, Duration lifetime) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject must not be blank");
        }
        if (issuedAt == null || lifetime == null || lifetime.isZero() || lifetime.isNegative()) {
            throw new IllegalArgumentException("issue time and a positive lifetime are required");
        }
        calls.add(new Call(subject, issuedAt, lifetime));
        return "fake-token-for-" + subject;
    }

    public List<Call> calls() {
        return List.copyOf(calls);
    }
}
