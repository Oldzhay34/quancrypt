package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.CryptoUsageSpecs;

/** P1: replace RSA encryption, key wrap and application-level key agreement with a KEM-DEM scheme (D-151). */
public final class KemDemEncryptionStrategy extends AbstractMigrationStrategy {

    public KemDemEncryptionStrategy() {
        super(StrategyCode.KEM_DEM_ENCRYPTION);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P1 && CryptoUsageSpecs.KEY_ESTABLISHMENT_USAGE.isSatisfiedBy(facts.usage());
    }
}
