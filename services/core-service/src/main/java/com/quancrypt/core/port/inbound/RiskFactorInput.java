package com.quancrypt.core.port.inbound;

import java.math.BigDecimal;

/** One SHAP contribution, in order of influence. */
public record RiskFactorInput(String featureName, BigDecimal shapValue) {
}
