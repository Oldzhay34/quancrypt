package com.quancrypt.core.domain.exception;

/** The scan already has a plan (unique constraint on the scan). */
public final class PlanAlreadyExistsException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public PlanAlreadyExistsException() {
        super("the scan already has a plan");
    }
}
