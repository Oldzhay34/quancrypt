package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;

/** Risk factor (schema RiskFactor); also the response item. */
public record RiskFactorDto(@NotNull @Pattern(regexp = "^[a-z][a-z0-9_]{0,99}$") String featureName, @NotNull @DecimalMin("-999.999999") @DecimalMax("999.999999") BigDecimal shapValue) {
}
