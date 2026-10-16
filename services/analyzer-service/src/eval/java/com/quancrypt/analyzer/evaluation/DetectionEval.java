package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Entry point of the detectionEval Gradle task: measures the Java plugin against the QBank golden inventory and writes
 * the report. The benchmark part is not measured yet: the user skipped it in P3.2 (D-191), so no benchmark file format
 * has been read and no loader for one exists. The task fails when the QBank targets are missed.
 */
public final class DetectionEval {

    static final String BENCHMARK_NOT_MEASURED = """
            **Ölçülmedi.** Kullanıcı P3.2'de benchmark ölçümünü atladı (D-191): CryptoAPI-Bench ve OWASP Benchmark klasörlerinin yolu
            verilmedi, bu yüzden etiket dosyalarının biçimi görülmedi ve benchmark yükleyicileri yazılmadı. Eşleme kuralları
            `docs/data/benchmark-mapping.md` içinde TASLAK olarak durur ve gerçek dosyalara karşı doğrulanmamıştır. Puanlama kodu
            (`BenchmarkScore`: TP, FP, FN, recall, precision ve H1 eşiği) yazılmış ve sentetik vakalarla sınanmıştır. H1 durumu: BİLİNMİYOR.
            Ölçmek için: benchmark klasörlerini `DATASETS_ROOT` olarak vermek, kuralları etiket dosyalarına göre doğrulatmak ve yükleyicileri yazmak gerekir.
            """;

    static final String PERFORMANCE_NOT_MEASURED = """
            ## 5. Performans (NFR-01: ≤ 300 sn)

            **Ölçülmedi.** Performans projesinin yolu verilmedi (D-198). Ölçmek için yaklaşık 50.000 satırlık bir Java projesiyle:
            `./gradlew detectionEval -Pquancrypt.perf.root=<proje yolu>`.
            """;
    private static final String PERFORMANCE_HEADING = "## 5. Performans";

    private DetectionEval() {
    }

    public static void main(String[] args) throws Exception {
        CanonicalNames names = new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
        QbankEvaluation.Run run = QbankEvaluation.run(JavaSpringPlugins.standard(names), Path.of(System.getProperty("quancrypt.reference.dir")),
                Path.of(System.getProperty("quancrypt.expected.dir")));
        Path report = Path.of(System.getProperty("quancrypt.report.file"));
        Files.createDirectories(Objects.requireNonNull(report.getParent(), "the report file needs a directory"));
        String performance = performanceSection(report);
        TopologyEvaluation.Run topology = TopologyEvaluation.run(JavaSpringPlugins.standard(names), Path.of(System.getProperty("quancrypt.reference.dir")),
                Path.of(System.getProperty("quancrypt.expected.dir")));
        Files.writeString(report, DetectionReport.render(run, BENCHMARK_NOT_MEASURED) + "\n" + performance.stripTrailing() + "\n\n"
                + TopologyEvaluation.render(topology), StandardCharsets.UTF_8);
        GoldenComparison.Result result = run.comparison();
        System.out.println("QBank: recall=" + result.recall() + " precision=" + result.precision() + " report=" + report);
        System.out.println("QBank topology: " + (topology.matches() ? "matches the golden file" : "DIFFERS: " + topology.edgeDifferences() + topology.nodeDifferences()));
        if (result.recall() < 1.0 || result.precision() < 0.95 || !result.priorityMismatches().isEmpty() || !topology.matches()) {
            throw new IllegalStateException("QBank targets missed: see " + report);
        }
    }

    /**
     * The performance section: measured when a project path is given, otherwise the section of the existing report stays
     * (a run without a path must not erase an earlier measurement), and only when there is none it says "not measured".
     */
    private static String performanceSection(Path report) throws Exception {
        String root = System.getProperty("quancrypt.perf.root", "");
        if (!root.isBlank()) {
            List<PerformanceMeasurement.Result> results = new ArrayList<>();
            for (String path : root.split(",")) {
                PerformanceMeasurement.Result result = PerformanceMeasurement.measure(Path.of(path.strip()), 3);
                System.out.println("Performance " + result.project() + ": " + result.runsMs() + " ms, " + result.javaLines() + " Java lines");
                results.add(result);
            }
            return PerformanceMeasurement.render(results);
        }
        if (Files.exists(report)) {
            String existing = Files.readString(report, StandardCharsets.UTF_8);
            int start = existing.indexOf(PERFORMANCE_HEADING);
            int end = existing.indexOf("\n## 6.", start);
            String section = start < 0 ? "" : end < 0 ? existing.substring(start) : existing.substring(start, end);
            if (start >= 0 && !section.contains("**Ölçülmedi.**")) {
                return section;
            }
        }
        return PERFORMANCE_NOT_MEASURED;
    }
}
