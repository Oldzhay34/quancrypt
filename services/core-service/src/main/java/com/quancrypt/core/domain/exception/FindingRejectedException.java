package com.quancrypt.core.domain.exception;

/** A finding must not be recorded: its priority disagrees with the table, or it needs no migration (D-149, D-151). */
public final class FindingRejectedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    /** Why the finding was rejected. */
    public enum Reason {
        PRIORITY_MISMATCH,
        NO_MIGRATION_NEEDED,
        NO_STRATEGY
    }

    private final Reason reason;

    public FindingRejectedException(Reason reason, String detail) {
        super(detail);
        this.reason = reason;
    }

    public Reason reason() {
        return reason;
    }
}
