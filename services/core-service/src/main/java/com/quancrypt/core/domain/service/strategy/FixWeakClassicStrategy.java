package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;

/** P0: replace weak classic crypto (MD5/SHA-1 signatures, DES/3DES, ECB, short RSA keys, PKCS#1 v1.5). */
public final class FixWeakClassicStrategy extends AbstractMigrationStrategy {

    public FixWeakClassicStrategy() {
        super(StrategyCode.FIX_WEAK_CLASSIC);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P0;
    }
}
