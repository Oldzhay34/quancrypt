package com.quancrypt.core.domain.model;

import java.util.Set;

/** The VERIFIED state of a plan item. */
public final class VerifiedState implements PlanItemState {

    private static final Set<PlanItemStateCode> TARGETS = Set.of();

    @Override
    public PlanItemStateCode code() {
        return PlanItemStateCode.VERIFIED;
    }

    @Override
    public Set<PlanItemStateCode> allowedTargets() {
        return TARGETS;
    }
}
