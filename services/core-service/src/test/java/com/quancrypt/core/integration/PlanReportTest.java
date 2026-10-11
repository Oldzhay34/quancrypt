package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.integration.support.ApiClient.Reply;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.FindingInput;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/** The report served over HTTP: its numbers equal what the database holds (D-164: every number comes from the database). */
class PlanReportTest extends IntegrationTest {

    private FindingInput finding(String path, String symbol, String algorithm, String usage, String priority, Integer keySize) {
        return new FindingInput(path, symbol, algorithm, usage, "CODE", priority, Optional.ofNullable(keySize), Optional.of(5), Optional.of(6), 0.9, "STATIC");
    }

    private UUID planWithThreeItems() {
        UUID projectId = projectWithConsent("/work/report");
        jdbc.sql("INSERT INTO project_runtime_profile (id, project_id, sequence_no, java_version, spring_boot_version, recorded_at) "
                + "VALUES (gen_random_uuid(), :p, 1, '17', '3.2.0', now())").param("p", projectId).update();
        UUID scanId = runningScan(projectId);
        List<UUID> ids = recordFindings.execute(new RecordFindingsCommand(scanId, List.of(
                finding("src/main/java/Tls.java", "Tls#handshake", "RSA", "TLS_KEY_EXCHANGE", "P1", 2048),
                finding("src/main/java/Crypto.java", "Crypto#wrap", "RSA", "ENCRYPTION", "P1", 2048),
                finding("src/main/java/Token.java", "Token#sign", "RSA", "TOKEN_SIGNATURE", "P3", 2048)), Optional.empty(), "UI")).createdIds();
        complete(scanId);
        plan(scanId, ids);
        UUID itemId = jdbc.sql("SELECT pi.id FROM plan_item pi JOIN finding f ON f.id = pi.finding_id WHERE f.symbol = 'Tls#handshake'")
                .query(UUID.class).single();
        transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, Optional.empty(), "UI"));
        return scanId;
    }

    private String count(String sql) {
        return jdbc.sql(sql).query((rs, n) -> rs.getString(1) + " " + rs.getLong(2)).list().stream().collect(Collectors.joining(", "));
    }

    @Test
    void everyNumberOfTheReportEqualsTheDatabase() {
        UUID scanId = planWithThreeItems();

        Reply report = api().get("/api/v1/scans/" + scanId + "/plan/report").bearer(SESSION_TOKEN).send();
        String md = report.text();

        assertThat(report.status()).isEqualTo(200);
        assertThat(report.header("content-type")).startsWith("text/markdown");
        long total = jdbc.sql("SELECT count(*) FROM plan_item").query(Long.class).single();
        assertThat(md).contains("- Toplam madde: " + total);
        String byClass = jdbc.sql("""
                SELECT rc.code, count(v.plan_item_id) FROM risk_class rc LEFT JOIN v_plan_item_risk v ON v.risk_class = rc.code
                GROUP BY rc.code, rc.sort_order ORDER BY rc.sort_order""").query((rs, n) -> rs.getString(1) + " " + rs.getLong(2)).list()
                .stream().collect(Collectors.joining(", "));
        assertThat(md).contains("- Risk sınıfına göre: " + byClass);
        assertThat(md).contains("- Efora göre: " + count("SELECT 'S', count(*) FROM plan_item WHERE effort = 'S'") + ", "
                + count("SELECT 'M', count(*) FROM plan_item WHERE effort = 'M'") + ", " + count("SELECT 'L', count(*) FROM plan_item WHERE effort = 'L'"));
        String byState = jdbc.sql("""
                SELECT s.code, count(pi.id) FROM plan_item_state s LEFT JOIN plan_item pi ON pi.state = s.code
                GROUP BY s.code, s.sort_order ORDER BY s.sort_order""").query((rs, n) -> rs.getString(1) + " " + rs.getLong(2)).list()
                .stream().collect(Collectors.joining(", "));
        assertThat(md).contains("- Duruma göre: " + byState);
        String byStrategy = jdbc.sql("SELECT strategy, count(*) FROM plan_item GROUP BY strategy ORDER BY strategy")
                .query((rs, n) -> rs.getString(1) + " " + rs.getLong(2)).list().stream().collect(Collectors.joining(", "));
        assertThat(md).contains("- Stratejiye göre: " + byStrategy);
        assertThat(md).contains("Java 17, Spring Boot 3.2.0");
        long rows = md.lines().filter(l -> l.matches("\\| \\d+ \\| .*")).count();
        assertThat(rows).isEqualTo(total);
        List<String[]> items = jdbc.sql("SELECT f.symbol, pi.strategy, pi.effort, pi.state, pi.risk_score::text FROM plan_item pi JOIN finding f ON f.id = pi.finding_id")
                .query((rs, n) -> new String[] {rs.getString(1), rs.getString(2), rs.getString(3), rs.getString(4),
                    new BigDecimal(rs.getString(5)).setScale(4).toPlainString()}).list();
        for (String[] item : items) {
            String line = md.lines().filter(l -> l.startsWith("| ") && l.contains(item[0])).findFirst().orElseThrow();
            assertThat(line).contains(item[1]).contains(" " + item[2] + " ").contains(item[3]).contains(item[4]);
        }
    }

    @Test
    void englishIsServedOnRequest() {
        UUID scanId = planWithThreeItems();

        String md = api().get("/api/v1/scans/" + scanId + "/plan/report").bearer(SESSION_TOKEN).header("Accept-Language", "en").send().text();

        assertThat(md).startsWith("# Quancrypt migration plan report").contains("- Total items: 3").contains("## 6. References");
    }
}
