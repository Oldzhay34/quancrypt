package com.quancrypt.core.domain.model;

import java.math.BigDecimal;

/** One SHAP contribution to a risk score; rank 1 is the most influential. */
public record RiskFactor(int rank, String featureName, BigDecimal shapValue) {

    private static final BigDecimal LIMIT = new BigDecimal("999.999999");

    public RiskFactor {
        if (rank < 1) {
            throw new IllegalArgumentException("rank must be positive");
        }
        if (featureName == null || !featureName.matches("^[a-z][a-z0-9_]{0,99}$")) {
            throw new IllegalArgumentException("feature name must match [a-z][a-z0-9_]{0,99}");
        }
        if (shapValue.abs().compareTo(LIMIT) > 0) {
            throw new IllegalArgumentException("SHAP value is out of range");
        }
    }
}
