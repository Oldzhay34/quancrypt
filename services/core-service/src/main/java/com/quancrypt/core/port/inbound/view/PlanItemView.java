package com.quancrypt.core.port.inbound.view;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

/** A plan item; the risk class is derived from the score. */
public record PlanItemView(UUID id, UUID findingId, String strategy, String effort, BigDecimal riskScore, String riskClass, String state, int version, List<RiskFactorView> riskFactors) {

    public PlanItemView {
        riskFactors = List.copyOf(riskFactors);
    }
}
