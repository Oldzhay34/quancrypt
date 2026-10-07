package com.quancrypt.qbank.payment.port.outbound;

import java.util.Objects;

/** Why an account lookup failed; part of the AccountDirectory contract. */
public final class AccountLookupException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    /** The failure categories. */
    public enum Reason {
        /** The account does not exist. */
        NOT_FOUND,
        /** The account exists but the caller does not own it. */
        FORBIDDEN,
        /** The account service did not accept the caller's token. */
        UNAUTHORIZED,
        /** The account service is unreachable, failed, or its circuit breaker is open. */
        UNAVAILABLE
    }

    private final Reason reason;

    public AccountLookupException(Reason reason) {
        super("account lookup failed: " + reason);
        this.reason = Objects.requireNonNull(reason, "reason");
    }

    public Reason reason() {
        return reason;
    }
}
