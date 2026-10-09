package com.quancrypt.core.domain.model;

import java.util.Set;

/** The APPLIED state of a plan item. */
public final class AppliedState implements PlanItemState {

    private static final Set<PlanItemStateCode> TARGETS = Set.of(PlanItemStateCode.VERIFIED, PlanItemStateCode.ROLLED_BACK);

    @Override
    public PlanItemStateCode code() {
        return PlanItemStateCode.APPLIED;
    }

    @Override
    public Set<PlanItemStateCode> allowedTargets() {
        return TARGETS;
    }
}
