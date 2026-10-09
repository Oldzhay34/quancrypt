package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.CryptoUsageSpecs;
import java.util.List;

/** P3: certificates, mTLS authentication and keystores keep classic certificates beside a hybrid key exchange (D-151). */
public final class HybridKexClassicCertStrategy extends AbstractMigrationStrategy {

    public HybridKexClassicCertStrategy() {
        super(StrategyCode.HYBRID_KEX_CLASSIC_CERT);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P3
                && (CryptoUsageSpecs.IDENTITY_OR_CERTIFICATE_USAGE.isSatisfiedBy(facts.usage())
                || CryptoUsageSpecs.KEYSTORE_ASSET.isSatisfiedBy(facts.usage()));
    }

    @Override
    public StrategyPlan plan(FindingFacts facts) {
        List<PlanNote> notes = CryptoUsageSpecs.KEYSTORE_ASSET.isSatisfiedBy(facts.usage())
                ? List.of(PlanNote.KEYSTORE_CONTENT_NOT_INSPECTED) : List.of();
        return new StrategyPlan(code(), notes);
    }
}
