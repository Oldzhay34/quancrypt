package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.NotNull;

/** Body of TransitionPlanItem (schema PlanItemTransition). */
public record PlanItemTransitionInput(@NotNull String toState) {
}
