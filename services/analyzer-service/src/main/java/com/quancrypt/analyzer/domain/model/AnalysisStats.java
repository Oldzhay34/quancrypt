package com.quancrypt.analyzer.domain.model;

/** Counters of one analysis. */
public record AnalysisStats(int filesScanned, int findingsTotal, long durationMs) {

    public AnalysisStats {
        if (filesScanned < 0 || findingsTotal < 0 || durationMs < 0) {
            throw new IllegalArgumentException("analysis counters are not negative");
        }
    }
}
