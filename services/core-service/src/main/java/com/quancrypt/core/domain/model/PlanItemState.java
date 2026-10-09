package com.quancrypt.core.domain.model;

import com.quancrypt.core.domain.exception.IllegalStateTransitionException;
import java.util.Set;

/** State of a plan item (State pattern); each state is a class and knows the states it may move to. */
public interface PlanItemState {

    PlanItemStateCode code();

    Set<PlanItemStateCode> allowedTargets();

    default boolean canTransitionTo(PlanItemStateCode target) {
        return allowedTargets().contains(target);
    }

    /** The target state, or {@link IllegalStateTransitionException} when this state does not allow it. */
    default PlanItemState transitionTo(PlanItemStateCode target) {
        if (!canTransitionTo(target)) {
            throw new IllegalStateTransitionException(code(), target);
        }
        return PlanItemStates.of(target);
    }
}
