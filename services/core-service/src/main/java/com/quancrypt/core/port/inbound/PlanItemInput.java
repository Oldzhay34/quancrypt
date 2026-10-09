package com.quancrypt.core.port.inbound;

import java.util.List;
import java.util.UUID;

/** The risk assessment of one finding. */
public record PlanItemInput(UUID findingId, double riskScore, List<RiskFactorInput> riskFactors) {

    public PlanItemInput {
        riskFactors = List.copyOf(riskFactors);
    }
}
