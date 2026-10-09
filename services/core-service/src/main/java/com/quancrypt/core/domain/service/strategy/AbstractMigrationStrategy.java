package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.StrategyCode;
import java.util.List;

/** Base of the seven ordinary strategies: they stand down while a JDK upgrade is pending for the finding. */
abstract class AbstractMigrationStrategy implements MigrationStrategy {

    private final StrategyCode code;

    AbstractMigrationStrategy(StrategyCode code) {
        this.code = code;
    }

    @Override
    public final StrategyCode code() {
        return code;
    }

    @Override
    public final boolean supports(FindingFacts facts) {
        return facts.pendingUpgrade().isEmpty() && matches(facts);
    }

    abstract boolean matches(FindingFacts facts);

    @Override
    public StrategyPlan plan(FindingFacts facts) {
        return new StrategyPlan(code, List.of());
    }
}
