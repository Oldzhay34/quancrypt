package com.quancrypt.core.domain.model;

import java.util.Set;

/** The ROLLED_BACK state of a plan item. */
public final class RolledBackState implements PlanItemState {

    private static final Set<PlanItemStateCode> TARGETS = Set.of(PlanItemStateCode.PLANNED);

    @Override
    public PlanItemStateCode code() {
        return PlanItemStateCode.ROLLED_BACK;
    }

    @Override
    public Set<PlanItemStateCode> allowedTargets() {
        return TARGETS;
    }
}
