package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.StrategyCode;

/** Effort estimate: the strategy's base effort, one grade higher with five or more call sites (D-124). */
public final class EffortPolicy {

    public static final int CALL_SITE_THRESHOLD = 5;

    public Effort estimate(StrategyCode strategy, int callSiteCount) {
        Effort base = strategy.baseEffort();
        return callSiteCount >= CALL_SITE_THRESHOLD ? base.raised() : base;
    }
}
