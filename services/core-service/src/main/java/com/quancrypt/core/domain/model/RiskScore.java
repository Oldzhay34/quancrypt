package com.quancrypt.core.domain.model;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** A risk score between 0 and 1 with four decimals (Model A output, D-128). */
public record RiskScore(BigDecimal value) {

    public RiskScore {
        value = value.setScale(4, RoundingMode.HALF_UP);
        if (value.signum() < 0 || value.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("risk score must be between 0 and 1");
        }
    }

    public static RiskScore of(double score) {
        if (Double.isNaN(score)) {
            throw new IllegalArgumentException("risk score must be a number");
        }
        return new RiskScore(BigDecimal.valueOf(score));
    }
}
