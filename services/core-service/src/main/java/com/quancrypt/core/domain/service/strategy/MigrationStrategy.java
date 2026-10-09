package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.StrategyCode;

/** One migration strategy; new strategies are new classes (Open/Closed). Commands arrive with phase 8, not before. */
public interface MigrationStrategy {

    StrategyCode code();

    boolean supports(FindingFacts facts);

    StrategyPlan plan(FindingFacts facts);
}
