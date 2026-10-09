package com.quancrypt.core.domain.service;

import com.quancrypt.core.domain.exception.NoStrategyException;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import com.quancrypt.core.domain.service.strategy.MigrationStrategy;
import java.util.List;

/** Holds every migration strategy it is given (Open/Closed) and finds the one that supports a finding. */
public final class StrategyRegistry {

    private final List<MigrationStrategy> strategies;

    public StrategyRegistry(List<MigrationStrategy> strategies) {
        this.strategies = List.copyOf(strategies);
    }

    /** The only strategy that supports the facts; throws when none or several do. */
    public MigrationStrategy select(FindingFacts facts) {
        List<MigrationStrategy> supporting = strategies.stream().filter(s -> s.supports(facts)).toList();
        if (supporting.size() != 1) {
            throw new NoStrategyException(supporting.isEmpty()
                    ? "no migration strategy supports priority " + facts.priority() + " and usage " + facts.usage().usage()
                    : "several migration strategies support the same finding: " + supporting.stream().map(MigrationStrategy::code).toList());
        }
        return supporting.get(0);
    }

    public boolean isRegistered(StrategyCode code) {
        return strategies.stream().anyMatch(s -> s.code() == code);
    }
}
