package com.quancrypt.core.domain.model;

import java.util.Set;

/** The DISCOVERED state of a plan item. */
public final class DiscoveredState implements PlanItemState {

    private static final Set<PlanItemStateCode> TARGETS = Set.of(PlanItemStateCode.PLANNED);

    @Override
    public PlanItemStateCode code() {
        return PlanItemStateCode.DISCOVERED;
    }

    @Override
    public Set<PlanItemStateCode> allowedTargets() {
        return TARGETS;
    }
}
