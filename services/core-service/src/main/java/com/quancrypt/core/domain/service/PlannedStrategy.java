package com.quancrypt.core.domain.service;

import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.service.strategy.PlanNote;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;

/** The planner's answer for one finding: strategy, effort and notes, plus what a JDK upgrade replaced. */
public record PlannedStrategy(
        StrategyCode code,
        Effort effort,
        List<PlanNote> notes,
        Optional<StrategyCode> replacedStrategy,
        OptionalInt requiredJavaMajor) {

    public PlannedStrategy {
        notes = List.copyOf(notes);
    }
}
