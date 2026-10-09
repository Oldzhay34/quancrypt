package com.quancrypt.core.domain.service;

import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.EffortPolicy;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy.UnmetRequirement;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import com.quancrypt.core.domain.service.strategy.MigrationStrategy;
import com.quancrypt.core.domain.service.strategy.PlanNote;
import com.quancrypt.core.domain.service.strategy.StrategyPlan;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;

/** Chooses a finding's strategy, swaps it for JDK_UPGRADE when the project's Java is too old, and estimates the effort. */
public final class StrategyPlanner {

    private final StrategyRegistry registry;
    private final JdkRequirementPolicy jdkPolicy;
    private final EffortPolicy effortPolicy;

    public StrategyPlanner(StrategyRegistry registry, JdkRequirementPolicy jdkPolicy, EffortPolicy effortPolicy) {
        this.registry = registry;
        this.jdkPolicy = jdkPolicy;
        this.effortPolicy = effortPolicy;
    }

    public PlannedStrategy plan(FindingFacts facts) {
        MigrationStrategy intended = registry.select(facts);
        Optional<UnmetRequirement> unmet = jdkPolicy.unmet(intended.code(), facts.javaVersion());
        FindingFacts effective = unmet.map(facts::withPendingUpgrade).orElse(facts);
        MigrationStrategy chosen = unmet.isPresent() ? registry.select(effective) : intended;
        StrategyPlan plan = chosen.plan(effective);
        List<PlanNote> notes = new ArrayList<>(plan.notes());
        if (facts.javaVersion().isEmpty() && jdkPolicy.requiredMajor(intended.code()).isPresent()) {
            notes.add(PlanNote.JAVA_VERSION_UNKNOWN);
        }
        StrategyCode code = plan.code();
        return new PlannedStrategy(
                code,
                effortPolicy.estimate(code, facts.callSiteCount()),
                notes,
                unmet.map(UnmetRequirement::intended),
                unmet.map(u -> OptionalInt.of(u.requiredMajor())).orElse(OptionalInt.empty()));
    }
}
