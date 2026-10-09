package com.quancrypt.core.port.inbound.view;

import java.math.BigDecimal;

/** One SHAP contribution to a risk score. */
public record RiskFactorView(int rank, String featureName, BigDecimal shapValue) {
}
