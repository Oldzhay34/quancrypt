package com.quancrypt.core.domain.model;

/** Migration strategy code list with the base effort of each strategy (crypto-domain, D-124). */
public enum StrategyCode {
    FIX_WEAK_CLASSIC(Effort.S),
    HYBRID_TLS_KEX(Effort.M),
    KEM_DEM_ENCRYPTION(Effort.L),
    DEVICE_HYBRID_TLS(Effort.L),
    PQ_SIGNATURE(Effort.L),
    KEEP_SHORT_LIVED_TOKEN(Effort.S),
    HYBRID_KEX_CLASSIC_CERT(Effort.S),
    JDK_UPGRADE(Effort.M);

    private final Effort baseEffort;

    StrategyCode(Effort baseEffort) {
        this.baseEffort = baseEffort;
    }

    public Effort baseEffort() {
        return baseEffort;
    }
}
