package com.quancrypt.qbank.account.port.outbound;

import java.time.Duration;
import java.time.Instant;

/** Issues signed access tokens. */
public interface TokenIssuer {

    /**
     * Issues a token for the subject.
     *
     * @param subject the authenticated username; must not be blank
     * @param issuedAt the issue time
     * @param lifetime the validity period; must be positive
     * @return the compact serialized token
     * @throws IllegalArgumentException when an argument violates the preconditions above
     */
    String issue(String subject, Instant issuedAt, Duration lifetime);
}
