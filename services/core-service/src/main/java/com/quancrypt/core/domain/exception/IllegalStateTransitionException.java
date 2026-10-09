package com.quancrypt.core.domain.exception;

import com.quancrypt.core.domain.model.PlanItemStateCode;

/** A plan item was asked to move to a state its current state does not allow. */
public final class IllegalStateTransitionException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final PlanItemStateCode from;
    private final PlanItemStateCode to;

    public IllegalStateTransitionException(PlanItemStateCode from, PlanItemStateCode to) {
        super("transition " + from + " -> " + to + " is not allowed");
        this.from = from;
        this.to = to;
    }

    public PlanItemStateCode from() {
        return from;
    }

    public PlanItemStateCode to() {
        return to;
    }
}
