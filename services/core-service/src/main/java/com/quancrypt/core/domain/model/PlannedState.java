package com.quancrypt.core.domain.model;

import java.util.Set;

/** The PLANNED state of a plan item. */
public final class PlannedState implements PlanItemState {

    private static final Set<PlanItemStateCode> TARGETS = Set.of(PlanItemStateCode.APPROVED);

    @Override
    public PlanItemStateCode code() {
        return PlanItemStateCode.PLANNED;
    }

    @Override
    public Set<PlanItemStateCode> allowedTargets() {
        return TARGETS;
    }
}
