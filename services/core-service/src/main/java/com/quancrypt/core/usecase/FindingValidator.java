package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.exception.FindingRejectedException;
import com.quancrypt.core.domain.exception.NoStrategyException;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.policy.PriorityPolicy;
import com.quancrypt.core.domain.service.StrategyRegistry;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import java.util.Optional;

/** Checks that a finding may be recorded: its priority agrees with the table and some strategy can plan it (D-149). */
public final class FindingValidator {

    private final PriorityPolicy priorityPolicy;
    private final StrategyRegistry registry;

    public FindingValidator(PriorityPolicy priorityPolicy, StrategyRegistry registry) {
        this.priorityPolicy = priorityPolicy;
        this.registry = registry;
    }

    /** The priority to store; throws a validation failure when the finding must be rejected. */
    Priority acceptedPriority(CryptoUsage usage, Priority supplied) {
        Priority priority;
        try {
            priority = priorityPolicy.accept(usage, supplied);
        } catch (FindingRejectedException e) {
            throw Fail.validation(e.getMessage());
        }
        try {
            registry.select(new FindingFacts(usage, priority, false, 0, Optional.empty()));
        } catch (NoStrategyException e) {
            throw Fail.validation("the finding cannot be planned: " + e.getMessage());
        }
        return priority;
    }
}
