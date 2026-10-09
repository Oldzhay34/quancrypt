package com.quancrypt.core.port.inbound.view;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

/** One row of the plan report. */
public record PlanReportItemView(String path, String symbol, String strategy, String effort, BigDecimal riskScore, String riskClass, String state, List<String> noteCodes, Optional<String> replacedStrategy, List<RiskFactorView> riskFactors) {

    public PlanReportItemView {
        noteCodes = List.copyOf(noteCodes);
        riskFactors = List.copyOf(riskFactors);
    }
}
