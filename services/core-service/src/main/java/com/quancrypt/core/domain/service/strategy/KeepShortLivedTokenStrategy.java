package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.CryptoUsageSpecs;

/** P3: short-lived tokens (JWT RS256) stay as they are for now; a key kept in a keystore is a keystore asset (D-151c). */
public final class KeepShortLivedTokenStrategy extends AbstractMigrationStrategy {

    public KeepShortLivedTokenStrategy() {
        super(StrategyCode.KEEP_SHORT_LIVED_TOKEN);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P3 && CryptoUsageSpecs.TOKEN_SIGNATURE_USAGE.isSatisfiedBy(facts.usage())
                && !CryptoUsageSpecs.KEYSTORE_ASSET.isSatisfiedBy(facts.usage());
    }
}
