package com.quancrypt.core.facade;

import com.quancrypt.core.port.inbound.view.ClarificationAnswerView;
import com.quancrypt.core.port.inbound.view.PlanReportItemView;
import com.quancrypt.core.port.inbound.view.PlanReportView;
import com.quancrypt.core.port.inbound.view.RiskFactorView;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * Renders the plan report model as Markdown following docs/data/plan-report-template.md. Every number, name and code
 * comes from the model (the database); only headings, labels and the fixed note sentences are text of this class.
 */
final class PlanReportRenderer {

    private static final List<String> RISK_CLASSES = List.of("CRITICAL", "HIGH", "MEDIUM", "LOW");
    private static final List<String> EFFORTS = List.of("S", "M", "L");
    private static final List<String> STATES = List.of("DISCOVERED", "PLANNED", "APPROVED", "APPLIED", "VERIFIED", "ROLLED_BACK");

    /** The language of a report: Turkish unless English is asked for. */
    enum Language {
        TR, EN;

        static Language of(String acceptLanguage) {
            if (acceptLanguage != null && acceptLanguage.strip().toLowerCase(Locale.ROOT).startsWith("en")) {
                return EN;
            }
            return TR;
        }
    }

    private final Language lang;

    PlanReportRenderer(Language lang) {
        this.lang = lang;
    }

    String render(PlanReportView report) {
        StringBuilder md = new StringBuilder(4096);
        md.append("# ").append(t("Quancrypt geçiş planı raporu", "Quancrypt migration plan report")).append("\n\n");
        summary(md, report);
        table(md, report);
        details(md, report);
        jdk(md, report);
        answers(md, report.answers());
        references(md);
        return md.toString();
    }

    private void summary(StringBuilder md, PlanReportView r) {
        md.append("## ").append(t("1. Özet", "1. Summary")).append("\n\n");
        var scan = r.scan();
        md.append("- ").append(t("Tarama", "Scan")).append(": ").append(scan.id()).append(", ").append(scan.status()).append(", ")
                .append(scan.startedAt()).append(" – ").append(scan.completedAt().map(Object::toString).orElse(t("sürüyor", "running"))).append('\n');
        md.append("- ").append(t("Plan", "Plan")).append(": ").append(r.plan().id()).append(", ").append(r.plan().createdAt()).append('\n');
        md.append("- ").append(t("Çalışma zamanı", "Runtime")).append(": ").append(runtime(r.runtimeProfile())).append('\n');
        md.append("- ").append(t("Toplam madde", "Total items")).append(": ").append(r.items().size()).append('\n');
        md.append("- ").append(t("Risk sınıfına göre", "By risk class")).append(": ")
                .append(counts(RISK_CLASSES, r.items().stream().map(PlanReportItemView::riskClass).toList())).append('\n');
        md.append("- ").append(t("Efora göre", "By effort")).append(": ")
                .append(counts(EFFORTS, r.items().stream().map(PlanReportItemView::effort).toList())).append('\n');
        md.append("- ").append(t("Duruma göre", "By state")).append(": ")
                .append(counts(STATES, r.items().stream().map(PlanReportItemView::state).toList())).append('\n');
        Map<String, Long> byStrategy = new TreeMap<>(r.items().stream()
                .collect(Collectors.groupingBy(PlanReportItemView::strategy, Collectors.counting())));
        md.append("- ").append(t("Stratejiye göre", "By strategy")).append(": ")
                .append(byStrategy.isEmpty() ? t("yok", "none")
                        : byStrategy.entrySet().stream().map(e -> e.getKey() + " " + e.getValue()).collect(Collectors.joining(", ")))
                .append("\n\n");
    }

    private String runtime(Optional<RuntimeProfileView> profile) {
        return profile.map(p -> "Java " + p.javaVersion() + p.springBootVersion().map(v -> ", Spring Boot " + v).orElse(""))
                .orElse(t("bilinmiyor", "unknown"));
    }

    private static String counts(List<String> order, List<String> values) {
        Map<String, Long> counted = values.stream().collect(Collectors.groupingBy(v -> v, Collectors.counting()));
        return order.stream().map(k -> k + " " + counted.getOrDefault(k, 0L)).collect(Collectors.joining(", "));
    }

    private void table(StringBuilder md, PlanReportView r) {
        md.append("## ").append(t("2. Maddeler (riske göre sıralı)", "2. Items (ordered by risk)")).append("\n\n");
        if (r.items().isEmpty()) {
            md.append(t("Madde yok.", "No items.")).append("\n\n");
            return;
        }
        md.append("| # | ").append(t("Dosya", "File")).append(" | ").append(t("Sembol", "Symbol")).append(" | ")
                .append(t("Risk skoru", "Risk score")).append(" | ").append(t("Risk sınıfı", "Risk class")).append(" | ")
                .append(t("Strateji", "Strategy")).append(" | ").append(t("Efor", "Effort")).append(" | ").append(t("Durum", "State"))
                .append(" |\n|---|---|---|---|---|---|---|---|\n");
        int n = 1;
        for (PlanReportItemView item : sorted(r)) {
            md.append("| ").append(n++).append(" | ").append(cell(item.path())).append(" | ").append(cell(item.symbol())).append(" | ")
                    .append(score(item)).append(" | ").append(item.riskClass()).append(" | ").append(item.strategy()).append(" | ")
                    .append(item.effort()).append(" | ").append(item.state()).append(" |\n");
        }
        md.append('\n');
    }

    private static List<PlanReportItemView> sorted(PlanReportView r) {
        return r.items().stream()
                .sorted(Comparator.comparing(PlanReportItemView::riskScore).reversed().thenComparing(PlanReportItemView::path))
                .toList();
    }

    private static String score(PlanReportItemView item) {
        return item.riskScore().setScale(4, RoundingMode.HALF_UP).toPlainString();
    }

    private void details(StringBuilder md, PlanReportView r) {
        md.append("## ").append(t("3. Madde ayrıntıları", "3. Item details")).append("\n\n");
        if (r.items().isEmpty()) {
            md.append(t("Madde yok.", "No items.")).append("\n\n");
            return;
        }
        int n = 1;
        for (PlanReportItemView item : sorted(r)) {
            md.append("### 3.").append(n++).append(". ").append(escape(item.path())).append(" — ").append(escape(item.symbol())).append("\n\n");
            md.append("- ").append(t("Strateji", "Strategy")).append(": ").append(item.strategy()).append('\n');
            item.replacedStrategy().ifPresent(s -> md.append("- ").append(t("Değiştirilen strateji", "Replaced strategy")).append(": ")
                    .append(s).append('\n'));
            md.append("- ").append(t("Efor", "Effort")).append(": ").append(item.effort()).append('\n');
            md.append("- ").append(t("Risk", "Risk")).append(": ").append(score(item)).append(" (").append(item.riskClass()).append(")\n");
            md.append("- ").append(t("Durum", "State")).append(": ").append(item.state()).append('\n');
            for (String note : item.noteCodes()) {
                md.append("- ").append(t("Not", "Note")).append(": ").append(note(note)).append('\n');
            }
            md.append("- ").append(t("Gerekçeler (SHAP)", "Reasons (SHAP)")).append(":\n");
            if (item.riskFactors().isEmpty()) {
                md.append("  ").append(t("Gerekçe kaydedilmemiş.", "No reason was recorded.")).append('\n');
            }
            for (RiskFactorView factor : item.riskFactors().stream().sorted(Comparator.comparingInt(RiskFactorView::rank)).toList()) {
                md.append("  ").append(factor.rank()).append(". ").append(factor.featureName()).append(": ")
                        .append(factor.shapValue().setScale(6, RoundingMode.HALF_UP).toPlainString()).append('\n');
            }
            md.append('\n');
        }
    }

    private void jdk(StringBuilder md, PlanReportView r) {
        md.append("## ").append(t("4. JDK önerisi", "4. JDK recommendation")).append("\n\n");
        List<PlanReportItemView> items = sorted(r);
        if (items.isEmpty()) {
            md.append(t("JDK ile ilgili öneri yok.", "There is no JDK recommendation.")).append("\n\n");
            return;
        }
        md.append("- ").append(t("Projenin Java sürümü", "Java version of the project")).append(": ")
                .append(r.runtimeProfile().map(RuntimeProfileView::javaVersion).orElse(t("bilinmiyor", "unknown"))).append('\n');
        md.append("- ").append(t("JDK yükseltmesi gereken maddeler (JDK_UPGRADE)", "Items that need a JDK upgrade (JDK_UPGRADE)")).append(": ")
                .append(positions(items, i -> "JDK_UPGRADE".equals(i.strategy()))).append('\n');
        md.append("- ").append(t("KEM-DEM veya PQ imza stratejili maddeler (en az JDK 24 gerekir)",
                "Items with a KEM-DEM or PQ signature strategy (JDK 24 or later is required)")).append(": ")
                .append(positions(items, i -> "KEM_DEM_ENCRYPTION".equals(i.strategy()) || "PQ_SIGNATURE".equals(i.strategy()))).append('\n');
        Map<String, Long> notes = new LinkedHashMap<>(new TreeMap<>(items.stream().flatMap(i -> i.noteCodes().stream())
                .collect(Collectors.groupingBy(c -> c, Collectors.counting()))));
        for (Map.Entry<String, Long> note : notes.entrySet()) {
            md.append("- ").append(note(note.getKey())).append(" (").append(note.getKey()).append(": ").append(note.getValue()).append(")\n");
        }
        md.append('\n');
    }

    private String positions(List<PlanReportItemView> sorted, Predicate<PlanReportItemView> match) {
        List<String> numbers = new ArrayList<>();
        for (int i = 0; i < sorted.size(); i++) {
            if (match.test(sorted.get(i))) {
                numbers.add(String.valueOf(i + 1));
            }
        }
        return numbers.isEmpty() ? t("yok", "none") : numbers.size() + " (#" + String.join(", #", numbers) + ")";
    }

    private void answers(StringBuilder md, List<ClarificationAnswerView> answers) {
        md.append("## ").append(t("5. Netleştirme yanıtları", "5. Clarification answers")).append("\n\n");
        if (answers.isEmpty()) {
            md.append(t("Yanıt verilmemiş.", "No answers were given.")).append("\n\n");
            return;
        }
        md.append("| ").append(t("Soru kodu", "Question code")).append(" | ").append(t("Seçenek", "Option")).append(" | ")
                .append(t("Açıklama", "Explanation")).append(" |\n|---|---|---|\n");
        for (ClarificationAnswerView a : answers) {
            md.append("| ").append(a.questionCode()).append(" | ").append(a.optionCode().orElse("")).append(" | ")
                    .append(cell(a.freeText().orElse(""))).append(" |\n");
        }
        md.append('\n');
    }

    private void references(StringBuilder md) {
        md.append("## ").append(t("6. Kaynaklar", "6. References")).append("\n\n");
        md.append("- ").append(t("FIPS 203 (ML-KEM), FIPS 204 (ML-DSA) ve FIPS 205 (SLH-DSA): 13 Ağustos 2024'te yayımlandı.",
                "FIPS 203 (ML-KEM), FIPS 204 (ML-DSA) and FIPS 205 (SLH-DSA): published on 13 August 2024.")).append('\n');
        md.append("- ").append(t("JEP 496 (ML-KEM) ve JEP 497 (ML-DSA): JDK 24.", "JEP 496 (ML-KEM) and JEP 497 (ML-DSA): JDK 24.")).append('\n');
        md.append("- ").append(t("JEP 527: JDK 27'de TLS 1.3 için hibrit X25519MLKEM768 varsayılan (JDK 27 tarihi 15 Eylül 2026).",
                "JEP 527: in JDK 27 the hybrid X25519MLKEM768 is the default for TLS 1.3 (JDK 27 date: 15 September 2026).")).append('\n');
    }

    private String note(String code) {
        return switch (code) {
            case "HYBRID_TLS_DEFAULT_ARRIVES_IN_JDK_27" -> t("JDK 27'de TLS 1.3 için hibrit X25519MLKEM768 grubu varsayılan olur (JEP 527).",
                    "In JDK 27 the hybrid X25519MLKEM768 group becomes the default for TLS 1.3 (JEP 527).");
            case "BOUNCY_CASTLE_ALTERNATIVE" -> t("JDK yükseltilemiyorsa Bouncy Castle ve BCJSSE yolu bir alternatiftir.",
                    "If the JDK cannot be upgraded, Bouncy Castle with BCJSSE is an alternative.");
            case "KEYSTORE_CONTENT_NOT_INSPECTED" -> t("Anahtar deposu içeriği açılmadı; yalnızca varlığı raporlandı.",
                    "The keystore content was not opened; only its presence is reported.");
            case "JAVA_VERSION_UNKNOWN" -> t("Java sürümü bilinmiyor; JDK gereksinimleri karşılanmış sayıldı.",
                    "The Java version is unknown; JDK requirements are treated as met.");
            default -> code;
        };
    }

    private String t(String tr, String en) {
        return lang == Language.TR ? tr : en;
    }

    /** Escapes Markdown control characters of values that come from the analyzed project. */
    static String escape(String text) {
        StringBuilder out = new StringBuilder(text.length() + 8);
        for (char c : text.toCharArray()) {
            if (c == '\n' || c == '\r') {
                out.append(' ');
            } else {
                if ("\\`*_[]<>|".indexOf(c) >= 0) {
                    out.append('\\');
                }
                out.append(c);
            }
        }
        return out.toString();
    }

    private static String cell(String text) {
        return escape(text);
    }
}
