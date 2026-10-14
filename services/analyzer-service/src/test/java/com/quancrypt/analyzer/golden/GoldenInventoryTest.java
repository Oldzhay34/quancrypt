package com.quancrypt.analyzer.golden;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.evaluation.GoldenComparison;
import com.quancrypt.analyzer.evaluation.QbankEvaluation;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * The Java plugin against the approved QBank golden inventory (D-123, D-184): every expected (file, algorithm family,
 * usage context) is found (recall 100%), at most 5% of what is found is not expected (precision at least 95%), and the
 * priorities agree with the inventory (the guard against drift from core-service's table, D-186).
 */
class GoldenInventoryTest {

    private static QbankEvaluation.Run run;

    @BeforeAll
    static void analyze() throws Exception {
        CanonicalNames names = new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
        run = QbankEvaluation.run(JavaSpringPlugins.standard(names), Path.of(System.getProperty("quancrypt.reference.dir")),
                Path.of(System.getProperty("quancrypt.expected.dir")));
    }

    private static String describe(GoldenComparison.Result result) {
        return "missing=" + result.missing() + "\nunexpected=" + result.unexpected() + "\npriority=" + result.priorityMismatches();
    }

    @Test
    void everyExpectedTripleIsFound() {
        assertThat(run.comparison().recall()).as(describe(run.comparison())).isEqualTo(1.0);
    }

    @Test
    void atLeastNinetyFivePercentOfWhatIsFoundIsExpected() {
        assertThat(run.comparison().precision()).as(describe(run.comparison())).isGreaterThanOrEqualTo(0.95);
    }

    @Test
    void prioritiesAgreeWithTheInventory() {
        assertThat(run.comparison().priorityMismatches()).as(describe(run.comparison())).isEmpty();
    }

    @Test
    void noDetectorFailedAndNoJavaFileWasSkipped() {
        assertThat(run.outcome().diagnostics().detectorFailures()).isEmpty();
        assertThat(run.outcome().diagnostics().javaFilesSkipped()).isZero();
        assertThat(run.outcome().diagnostics().javaFilesParsed()).isPositive();
    }

    @Test
    void onlyPythonEntriesAreOutOfScope() {
        assertThat(run.comparison().excluded()).hasSize(1).allMatch(entry -> entry.contains("paho_message_publisher.py"));
    }
}
