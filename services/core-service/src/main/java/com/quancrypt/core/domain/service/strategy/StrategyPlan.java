package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.StrategyCode;
import java.util.List;

/** What one strategy contributes to a plan item: its code and notes. */
public record StrategyPlan(StrategyCode code, List<PlanNote> notes) {

    public StrategyPlan {
        notes = List.copyOf(notes);
    }
}
