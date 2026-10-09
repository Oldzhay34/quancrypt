package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.StrategyCode;
import java.util.Map;

/** A migration plan was created for a scan (CreatePlan). */
public record PlanCreated(int itemCount, Map<StrategyCode, Integer> strategyCounts, Map<Effort, Integer> effortCounts)
        implements DomainEvent {

    public PlanCreated {
        strategyCounts = Map.copyOf(strategyCounts);
        effortCounts = Map.copyOf(effortCounts);
    }

    @Override
    public EventType type() {
        return EventType.PLAN_CREATED;
    }

    @Override
    public Map<String, Object> payload() {
        return Payloads.of(
                "item_count", itemCount,
                "strategy_counts", Payloads.counts(strategyCounts),
                "effort_counts", Payloads.counts(effortCounts));
    }
}
