package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Renders the detection evaluation as the Markdown report services/analyzer-service/docs/detection_eval.md. */
public final class DetectionReport {

    private DetectionReport() {
    }

    public static String render(QbankEvaluation.Run run, String benchmarkSection) {
        GoldenComparison.Result result = run.comparison();
        List<CryptoUsage> usages = run.outcome().usages();
        StringBuilder out = new StringBuilder();
        out.append("# Tespit değerlendirmesi (P3.2, P3.3, P3.4)\n\n");
        out.append("Bu dosya `./gradlew detectionEval` ile üretilir (analyzer-service). Elle düzenlenmez.\n\n");
        out.append("## 1. QBank altın envanteri\n\n");
        out.append("Karşılaştırma `(file, algorithm_family, usage_context)` üçlüsü üzerindedir (küme eşleşmesi). ");
        out.append("`TEST_CODE` bulguları bulunan tarafta yoktur; Python kayıtları Java eklentisinin kapsamı dışındadır (D-184).\n\n");
        out.append("**Not:** QBank hem geliştirme hem değerlendirme kümesidir (dedektörler bu envanterle ayarlandı); bu sonuç örneklem içidir ve ")
                .append("yabancı projelerdeki doğruluğu göstermez. Genelleme ölçümü benchmark alt kümesine bağlıdır ve ölçülmedi (bölüm 4).\n\n");
        out.append("| Ölçüt | Değer | Hedef | Durum |\n|---|---|---|---|\n");
        out.append(String.format(Locale.ROOT, "| Recall | %.1f%% (%d/%d) | 100%% | %s |%n", result.recall() * 100,
                result.expected().size() - result.missing().size(), result.expected().size(), result.recall() == 1.0 ? "Karşılandı" : "Karşılanmadı"));
        out.append(String.format(Locale.ROOT, "| Precision | %.1f%% (%d/%d) | ≥ 95%% | %s |%n", result.precision() * 100,
                result.found().size() - result.unexpected().size(), result.found().size(), result.precision() >= 0.95 ? "Karşılandı" : "Karşılanmadı"));
        out.append("| Öncelik uyumu | ").append(result.priorityMismatches().isEmpty() ? "tüm kayıtlarda aynı" : result.priorityMismatches().size() + " fark")
                .append(" | aynı | ").append(result.priorityMismatches().isEmpty() ? "Karşılandı" : "Karşılanmadı").append(" |\n\n");
        list(out, "Bulunamayan üçlüler", result.missing().stream().map(Triple::toString).toList());
        list(out, "Beklenmeyen üçlüler", result.unexpected().stream().map(Triple::toString).toList());
        list(out, "Öncelik farkları", result.priorityMismatches());
        list(out, "Karşılaştırma dışı bırakılan altın kayıtlar (Java eklentisi kapsamı dışı)", result.excluded());

        out.append("## 2. Bulgu dağılımı (QBank, test kodu dahil)\n\n");
        out.append("Toplam ").append(usages.size()).append(" bulgu. Aşağıdaki tablolar bulguların dedektöre, önceliğe ve konuma göre sayısıdır.\n\n");
        table(out, "Dedektör", count(usages, CryptoUsage::detectorId));
        table(out, "Öncelik", count(usages, u -> u.priority().name()));
        table(out, "Konum türü", count(usages, u -> u.evidence().locationKind().name()));
        table(out, "Kullanım bağlamı", count(usages, u -> u.usageContext().name()));

        out.append("## 3. Tanılar\n\n");
        var diagnostics = run.outcome().diagnostics();
        out.append("- Ayrıştırılan Java dosyası: ").append(diagnostics.javaFilesParsed()).append('\n');
        out.append("- Atlanan Java dosyası: ").append(diagnostics.javaFilesSkipped()).append('\n');
        out.append("- Dedektör hatası: ").append(diagnostics.detectorFailures().size()).append('\n');
        out.append("- Sözlükte olmayan ham ad: ").append(diagnostics.unresolvedNames().isEmpty() ? "yok" : String.join(", ", diagnostics.unresolvedNames()))
                .append("\n");
        out.append("- Build dosyalarında bulunan kripto kütüphanesi: ").append(run.outcome().libraries().size()).append("\n\n");

        out.append("## 4. Benchmark alt kümesi (H1: recall ≥ %90, precision ≥ %85)\n\n");
        out.append(benchmarkSection).append("\n");
        return out.toString();
    }

    private static void list(StringBuilder out, String title, List<String> items) {
        out.append("**").append(title).append(":** ");
        if (items.isEmpty()) {
            out.append("yok\n\n");
            return;
        }
        out.append('\n');
        items.forEach(item -> out.append("- `").append(item).append("`\n"));
        out.append('\n');
    }

    private static Map<String, Long> count(List<CryptoUsage> usages, Function<CryptoUsage, String> key) {
        return usages.stream().collect(Collectors.groupingBy(key, TreeMap::new, Collectors.counting()));
    }

    private static void table(StringBuilder out, String header, Map<String, Long> counts) {
        out.append("| ").append(header).append(" | Bulgu |\n|---|---|\n");
        counts.forEach((name, number) -> out.append("| ").append(name).append(" | ").append(number).append(" |\n"));
        out.append('\n');
    }
}
