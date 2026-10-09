package com.quancrypt.core.domain.model;

import java.util.Set;

/** The APPROVED state of a plan item. */
public final class ApprovedState implements PlanItemState {

    private static final Set<PlanItemStateCode> TARGETS = Set.of(PlanItemStateCode.APPLIED);

    @Override
    public PlanItemStateCode code() {
        return PlanItemStateCode.APPROVED;
    }

    @Override
    public Set<PlanItemStateCode> allowedTargets() {
        return TARGETS;
    }
}
