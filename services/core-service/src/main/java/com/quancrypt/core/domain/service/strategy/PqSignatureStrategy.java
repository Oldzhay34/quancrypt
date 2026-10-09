package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.CryptoUsageSpecs;

/** P2: move long-lived signatures (documents, audit records, software packages) to a post-quantum signature. */
public final class PqSignatureStrategy extends AbstractMigrationStrategy {

    public PqSignatureStrategy() {
        super(StrategyCode.PQ_SIGNATURE);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P2 && CryptoUsageSpecs.SIGNATURE_USAGE.isSatisfiedBy(facts.usage());
    }
}
