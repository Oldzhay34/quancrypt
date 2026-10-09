package com.quancrypt.core.domain.model;

import java.util.EnumMap;
import java.util.Map;

/** Registry of the six state singletons. */
public final class PlanItemStates {

    private static final Map<PlanItemStateCode, PlanItemState> BY_CODE = new EnumMap<>(PlanItemStateCode.class);

    static {
        for (PlanItemState state : new PlanItemState[] {
            new DiscoveredState(), new PlannedState(), new ApprovedState(),
            new AppliedState(), new VerifiedState(), new RolledBackState()}) {
            BY_CODE.put(state.code(), state);
        }
    }

    private PlanItemStates() {
    }

    public static PlanItemState of(PlanItemStateCode code) {
        return BY_CODE.get(code);
    }
}
