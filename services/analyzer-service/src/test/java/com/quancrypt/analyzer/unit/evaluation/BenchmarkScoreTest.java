package com.quancrypt.analyzer.unit.evaluation;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.evaluation.BenchmarkCase;
import com.quancrypt.analyzer.evaluation.BenchmarkScore;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/** The file-level scoring of the benchmark subset (mapping rule 6), on synthetic cases. */
class BenchmarkScoreTest {

    private static List<BenchmarkCase> cases(int tp, int fn, int fp, int tn) {
        List<BenchmarkCase> list = new ArrayList<>();
        for (int i = 0; i < tp; i++) {
            list.add(new BenchmarkCase("tp" + i, true, true));
        }
        for (int i = 0; i < fn; i++) {
            list.add(new BenchmarkCase("fn" + i, true, false));
        }
        for (int i = 0; i < fp; i++) {
            list.add(new BenchmarkCase("fp" + i, false, true));
        }
        for (int i = 0; i < tn; i++) {
            list.add(new BenchmarkCase("tn" + i, false, false));
        }
        return list;
    }

    @Test
    void casesAreCountedAsTruePositivesFalseNegativesFalsePositivesAndTrueNegatives() {
        BenchmarkScore score = BenchmarkScore.of(cases(9, 1, 2, 8));

        assertThat(score).isEqualTo(new BenchmarkScore(9, 2, 1, 8));
        assertThat(score.recall().orElseThrow()).isEqualTo(0.9);
        assertThat(score.precision().orElseThrow()).isEqualTo(9.0 / 11.0);
    }

    @Test
    void h1NeedsRecallOfNinetyAndPrecisionOfEightyFivePercent() {
        assertThat(BenchmarkScore.of(cases(9, 1, 1, 5)).meetsH1()).isTrue();
        assertThat(BenchmarkScore.of(cases(8, 2, 0, 5)).meetsH1()).isFalse();
        assertThat(BenchmarkScore.of(cases(17, 0, 3, 5)).meetsH1()).isTrue();
        assertThat(BenchmarkScore.of(cases(16, 0, 4, 5)).meetsH1()).isFalse();
    }

    @Test
    void withoutVulnerableFilesOrReportsTheNumbersAreUndefinedAndH1IsNotMet() {
        assertThat(BenchmarkScore.of(cases(0, 0, 0, 10)).recall()).isEmpty();
        assertThat(BenchmarkScore.of(cases(0, 0, 0, 10)).precision()).isEmpty();
        assertThat(BenchmarkScore.of(cases(0, 0, 0, 10)).meetsH1()).isFalse();
        assertThat(BenchmarkScore.of(cases(0, 5, 0, 0)).precision()).isEmpty();
    }
}
