package com.quancrypt.core.facade.dto;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

/** Plan item (schema PlanItem). */
public record PlanItemDto(UUID id, UUID findingId, String strategy, String effort, BigDecimal riskScore, String riskClass, String state, int version, List<RiskFactorDto> riskFactors) {

    public PlanItemDto {
        riskFactors = riskFactors == null ? null : List.copyOf(riskFactors);
    }
}

