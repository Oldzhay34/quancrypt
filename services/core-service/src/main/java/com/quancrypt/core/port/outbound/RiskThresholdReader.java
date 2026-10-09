package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.policy.RiskClassPolicy;

/** Reads the risk class thresholds of the lookup table. */
public interface RiskThresholdReader {

    RiskClassPolicy policy();
}
