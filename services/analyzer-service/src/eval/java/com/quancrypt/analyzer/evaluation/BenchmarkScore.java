package com.quancrypt.analyzer.evaluation;

import java.util.List;
import java.util.OptionalDouble;

/**
 * Recall and precision of the benchmark subset (rule 6 of the mapping): a vulnerable file with a P0 finding is a true
 * positive, one without is a false negative, a safe file with a P0 finding is a false positive. H1 asks for recall of at
 * least 90% and precision of at least 85%.
 */
public record BenchmarkScore(int truePositives, int falsePositives, int falseNegatives, int trueNegatives) {

    public static final double RECALL_TARGET = 0.90;
    public static final double PRECISION_TARGET = 0.85;

    public static BenchmarkScore of(List<BenchmarkCase> cases) {
        int tp = 0;
        int fp = 0;
        int fn = 0;
        int tn = 0;
        for (BenchmarkCase c : cases) {
            if (c.labelledVulnerable() && c.reportedP0()) {
                tp++;
            } else if (c.labelledVulnerable()) {
                fn++;
            } else if (c.reportedP0()) {
                fp++;
            } else {
                tn++;
            }
        }
        return new BenchmarkScore(tp, fp, fn, tn);
    }

    /** Empty when no vulnerable file exists (nothing to find). */
    public OptionalDouble recall() {
        int positives = truePositives + falseNegatives;
        return positives == 0 ? OptionalDouble.empty() : OptionalDouble.of((double) truePositives / positives);
    }

    /** Empty when the plugin reported nothing. */
    public OptionalDouble precision() {
        int reported = truePositives + falsePositives;
        return reported == 0 ? OptionalDouble.empty() : OptionalDouble.of((double) truePositives / reported);
    }

    /** Whether both numbers exist and reach the H1 targets. */
    public boolean meetsH1() {
        return recall().orElse(0) >= RECALL_TARGET && precision().orElse(0) >= PRECISION_TARGET;
    }
}
