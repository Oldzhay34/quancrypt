package com.quancrypt.core.domain.model;

import java.util.List;
import java.util.UUID;

/** One finding's migration plan: strategy and effort are a snapshot taken at plan time (D-130); optimistic version. */
public record PlanItem(
        UUID id,
        UUID planId,
        UUID findingId,
        StrategyCode strategy,
        Effort effort,
        RiskScore riskScore,
        PlanItemState state,
        int version,
        List<RiskFactor> riskFactors) {

    public PlanItem {
        riskFactors = List.copyOf(riskFactors);
    }

    public static PlanItem discovered(
            UUID id, UUID planId, UUID findingId, StrategyCode strategy, Effort effort, RiskScore score, List<RiskFactor> factors) {
        return new PlanItem(id, planId, findingId, strategy, effort, score, PlanItemStates.of(PlanItemStateCode.DISCOVERED), 0, factors);
    }

    /** Moves to the target state and bumps the version; throws when the state machine forbids it. */
    public PlanItem transitionTo(PlanItemStateCode target) {
        return new PlanItem(id, planId, findingId, strategy, effort, riskScore, state.transitionTo(target), version + 1, riskFactors);
    }
}
