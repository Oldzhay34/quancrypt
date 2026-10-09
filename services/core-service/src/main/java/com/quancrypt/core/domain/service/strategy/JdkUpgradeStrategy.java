package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.StrategyCode;
import java.util.List;

/** Supports a finding only while a JDK upgrade is pending for its intended strategy (D-133, D-150). */
public final class JdkUpgradeStrategy implements MigrationStrategy {

    @Override
    public StrategyCode code() {
        return StrategyCode.JDK_UPGRADE;
    }

    @Override
    public boolean supports(FindingFacts facts) {
        return facts.pendingUpgrade().isPresent();
    }

    @Override
    public StrategyPlan plan(FindingFacts facts) {
        return new StrategyPlan(StrategyCode.JDK_UPGRADE, List.of(PlanNote.BOUNCY_CASTLE_ALTERNATIVE));
    }
}
