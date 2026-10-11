package com.quancrypt.core.unit.facade;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.facade.PlanFacade;
import com.quancrypt.core.port.inbound.GetPlanReportQuery;
import com.quancrypt.core.port.inbound.GetPlanReportUseCase;
import com.quancrypt.core.port.inbound.view.ClarificationAnswerView;
import com.quancrypt.core.port.inbound.view.PlanReportItemView;
import com.quancrypt.core.port.inbound.view.PlanReportView;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.inbound.view.RiskFactorView;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import com.quancrypt.core.port.inbound.view.ScanView;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/**
 * The Markdown report follows docs/data/plan-report-template.md (D-164): the headings of the template, in order, in both
 * languages; every number is derived from the model; text from the analyzed project is escaped.
 */
class PlanReportRendererTest {

    private static final UUID SCAN = UUID.fromString("00000000-0000-0000-0000-0000000000a1");
    private static final Instant START = Instant.parse("2026-10-10T10:00:00Z");

    private static PlanReportItemView item(String path, String symbol, String strategy, String effort, String score, String riskClass,
            String state, List<String> notes, Optional<String> replaced, List<RiskFactorView> factors) {
        return new PlanReportItemView(path, symbol, strategy, effort, new BigDecimal(score), riskClass, state, notes, replaced, factors);
    }

    private static PlanReportView sample() {
        PlanView plan = new PlanView(UUID.fromString("00000000-0000-0000-0000-0000000000b1"), SCAN, START.plusSeconds(60), 4);
        ScanView scan = new ScanView(SCAN, UUID.fromString("00000000-0000-0000-0000-0000000000c1"), "COMPLETED", START, Optional.of(START.plusSeconds(30)),
                Optional.of(1));
        List<PlanReportItemView> items = List.of(
                item("src/main/java/Low.java", "Low#a", "KEEP_SHORT_LIVED_TOKEN", "S", "0.1000", "LOW", "PLANNED", List.of(), Optional.empty(), List.of()),
                item("src/main/java/Tls.java", "Tls#handshake", "HYBRID_TLS_KEX", "M", "0.9000", "CRITICAL", "APPROVED",
                        List.of("HYBRID_TLS_DEFAULT_ARRIVES_IN_JDK_27", "BOUNCY_CASTLE_ALTERNATIVE"), Optional.empty(),
                        List.of(new RiskFactorView(2, "exposure", new BigDecimal("-0.125000")), new RiskFactorView(1, "algorithm_weakness", new BigDecimal("0.400000")))),
                item("src/main/java/Kem.java", "Kem#wrap", "JDK_UPGRADE", "M", "0.6500", "HIGH", "PLANNED", List.of("JAVA_VERSION_UNKNOWN"),
                        Optional.of("KEM_DEM_ENCRYPTION"), List.of()),
                item("a|b`c.java", "x*y_z", "PQ_SIGNATURE", "L", "0.3500", "MEDIUM", "PLANNED", List.of("KEYSTORE_CONTENT_NOT_INSPECTED"),
                        Optional.empty(), List.of()));
        return new PlanReportView(plan, scan, Optional.of(new RuntimeProfileView(1, "17", Optional.of("3.2.0"), START, false)),
                List.of(new ClarificationAnswerView("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty()),
                        new ClarificationAnswerView("COMPLIANCE_REQUIREMENT", Optional.of("YES"), Optional.of("BDDK\nline | two"))),
                items);
    }

    private static PlanReportView empty() {
        PlanReportView s = sample();
        return new PlanReportView(new PlanView(s.plan().id(), SCAN, START, 0), s.scan(), Optional.empty(), List.of(), List.of());
    }

    private static String render(PlanReportView view, String language) {
        GetPlanReportUseCase useCase = (GetPlanReportQuery q) -> view;
        return new PlanFacade(null, null, null, useCase).report(SCAN, language);
    }

    private static List<String> headings(String markdown) {
        return markdown.lines().filter(l -> l.startsWith("#")).map(l -> l.replaceFirst("^(### 3\\.)\\d+\\. .*$", "### 3.n. ITEM")).toList();
    }

    private static List<String> templateHeadings(String resource) throws IOException {
        try (InputStream in = PlanReportRendererTest.class.getResourceAsStream(resource)) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).lines()
                    .map(l -> l.startsWith("### 3.n.") ? "### 3.n. ITEM" : l).toList();
        }
    }

    @Test
    void theHeadingsAreThoseOfTheTemplateInBothLanguages() throws IOException {
        List<String> tr = headings(render(sample(), null));
        List<String> en = headings(render(sample(), "en"));

        assertThat(tr.subList(0, 5)).isEqualTo(templateHeadings("/report/headings-tr.txt").subList(0, 5));
        assertThat(tr.subList(tr.size() - 3, tr.size())).isEqualTo(templateHeadings("/report/headings-tr.txt").subList(5, 8));
        assertThat(tr.stream().filter(h -> h.startsWith("### 3.n.")).count()).isEqualTo(4);
        assertThat(en.subList(0, 5)).isEqualTo(templateHeadings("/report/headings-en.txt").subList(0, 5));
        assertThat(en.subList(en.size() - 3, en.size())).isEqualTo(templateHeadings("/report/headings-en.txt").subList(5, 8));
    }

    @Test
    void anEmptyPlanKeepsEverySectionHeading() throws IOException {
        List<String> tr = headings(render(empty(), "tr"));

        assertThat(tr).isEqualTo(templateHeadings("/report/headings-tr.txt").stream().filter(h -> !h.startsWith("### 3.n.")).toList());
        assertThat(render(empty(), "tr")).contains("Madde yok.").contains("Yanıt verilmemiş.").contains("bilinmiyor");
    }

    @Test
    void everyNumberComesFromTheModel() {
        String md = render(sample(), "tr");

        assertThat(md).contains("- Toplam madde: 4");
        assertThat(md).contains("- Risk sınıfına göre: CRITICAL 1, HIGH 1, MEDIUM 1, LOW 1");
        assertThat(md).contains("- Efora göre: S 1, M 2, L 1");
        assertThat(md).contains("- Duruma göre: DISCOVERED 0, PLANNED 3, APPROVED 1, APPLIED 0, VERIFIED 0, ROLLED_BACK 0");
        assertThat(md).contains("HYBRID_TLS_KEX 1").contains("JDK_UPGRADE 1").contains("KEEP_SHORT_LIVED_TOKEN 1").contains("PQ_SIGNATURE 1");
        assertThat(md).contains("Java 17, Spring Boot 3.2.0");
        assertThat(md).contains("- Çalışma zamanı");
        assertThat(Pattern.compile("\\| \\d+ \\|").matcher(md).results().count()).isEqualTo(4);
    }

    @Test
    void itemsAreOrderedByRiskScoreAndShowTheirReasons() {
        String md = render(sample(), "en");

        assertThat(md.indexOf("Tls#handshake")).isLessThan(md.indexOf("Kem#wrap"));
        assertThat(md.indexOf("Kem#wrap")).isLessThan(md.indexOf("x\\*y\\_z"));
        assertThat(md.indexOf("x\\*y\\_z")).isLessThan(md.indexOf("Low#a"));
        assertThat(md).contains("| 1 | src/main/java/Tls.java | Tls#handshake | 0.9000 | CRITICAL | HYBRID_TLS_KEX | M | APPROVED |");
        assertThat(md).contains("  1. algorithm_weakness: 0.400000").contains("  2. exposure: -0.125000");
        assertThat(md).contains("Replaced strategy: KEM_DEM_ENCRYPTION").contains("No reason was recorded.");
    }

    @Test
    void jdkSectionListsTheAffectedItemsAndTheNotes() {
        String md = render(sample(), "en");

        assertThat(md).contains("Java version of the project: 17");
        assertThat(md).contains("Items that need a JDK upgrade (JDK_UPGRADE): 1 (#2)");
        assertThat(md).contains("Items with a KEM-DEM or PQ signature strategy (JDK 24 or later is required): 1 (#3)");
        assertThat(md).contains("(HYBRID_TLS_DEFAULT_ARRIVES_IN_JDK_27: 1)").contains("(BOUNCY_CASTLE_ALTERNATIVE: 1)")
                .contains("(KEYSTORE_CONTENT_NOT_INSPECTED: 1)").contains("(JAVA_VERSION_UNKNOWN: 1)");
        assertThat(md).contains("JEP 527").contains("FIPS 203").contains("JEP 496");
    }

    @Test
    void textOfTheAnalyzedProjectIsEscapedAndStaysOnOneLine() {
        String md = render(sample(), "tr");

        assertThat(md).contains("a\\|b\\`c.java").contains("| COMPLIANCE_REQUIREMENT | YES | BDDK line \\| two |");
        assertThat(md.lines().filter(l -> l.contains("BDDK"))).hasSize(1);
    }
}
