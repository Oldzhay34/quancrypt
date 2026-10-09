package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.model.RiskClass;
import com.quancrypt.core.domain.model.RiskScore;
import java.math.BigDecimal;
import java.util.EnumMap;
import java.util.Map;

/** Maps a risk score to a risk class with the thresholds of the lookup table (D-128); the classes are never stored. */
public final class RiskClassPolicy {

    private final Map<RiskClass, BigDecimal> minScores;

    public RiskClassPolicy(Map<RiskClass, BigDecimal> minScores) {
        if (!minScores.keySet().containsAll(java.util.List.of(RiskClass.values()))
                || minScores.get(RiskClass.LOW).signum() != 0) {
            throw new IllegalArgumentException("every risk class needs a threshold and LOW must start at 0");
        }
        this.minScores = new EnumMap<>(minScores);
    }

    /** The highest class whose threshold is at or below the score. */
    public RiskClass classify(RiskScore score) {
        RiskClass best = RiskClass.LOW;
        BigDecimal bestMin = BigDecimal.ZERO;
        for (Map.Entry<RiskClass, BigDecimal> entry : minScores.entrySet()) {
            BigDecimal min = entry.getValue();
            if (min.compareTo(score.value()) <= 0 && min.compareTo(bestMin) >= 0) {
                best = entry.getKey();
                bestMin = min;
            }
        }
        return best;
    }
}
