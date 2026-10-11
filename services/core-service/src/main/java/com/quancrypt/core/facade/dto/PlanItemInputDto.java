package com.quancrypt.core.facade.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

/** Plan item of CreatePlan (schema PlanItemInput). */
public record PlanItemInputDto(@NotNull UUID findingId, @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double riskScore, @NotNull @Size(max = 10) List<@NotNull @Valid RiskFactorDto> riskFactors) {

    public PlanItemInputDto {
        riskFactors = riskFactors == null ? null : List.copyOf(riskFactors);
    }
}

