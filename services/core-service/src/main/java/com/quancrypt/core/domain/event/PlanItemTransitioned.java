package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.StrategyCode;
import java.util.Map;

/** A plan item changed state (TransitionPlanItem). */
public record PlanItemTransitioned(StrategyCode strategy, Effort effort, PlanItemStateCode from, PlanItemStateCode to)
        implements DomainEvent {

    @Override
    public EventType type() {
        return EventType.PLAN_ITEM_TRANSITIONED;
    }

    @Override
    public Map<String, Object> payload() {
        return Payloads.of("strategy", strategy.name(), "effort", effort.name(), "from_state", from.name(), "to_state", to.name());
    }
}
