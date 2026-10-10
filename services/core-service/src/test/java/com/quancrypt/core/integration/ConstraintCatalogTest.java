package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * acid-3nf-database section 7, constraint tests: every CHECK, UNIQUE and FOREIGN KEY constraint of core_db (and the
 * partial unique index) is violated once, as core_db_app, and the database must name exactly that constraint. The
 * violating statement is derived from the catalog: a FOREIGN KEY column gets a value with no parent, a UNIQUE key is
 * copied into a new row, a CHECK gets a value outside its rule. Each statement fails on its own, so the fixture stays.
 */
class ConstraintCatalogTest {

    private static final String PARTIAL_UNIQUE_INDEX = "uq_scan_one_running_per_project";

    /** Violations of the CHECK constraints that are not a lookup's sort_order rule. */
    private static final Map<String, String> CHECK_VIOLATIONS = Map.ofEntries(
            Map.entry("ck_project_project_key_hex", "UPDATE project SET project_key = repeat('G', 64)"),
            Map.entry("ck_project_display_name_not_blank", "UPDATE project SET display_name = '   '"),
            Map.entry("ck_project_runtime_profile_sequence_positive", "UPDATE project_runtime_profile SET sequence_no = 0 WHERE sequence_no = 2"),
            Map.entry("ck_privacy_notice_version_positive", "UPDATE privacy_notice SET version = 0"),
            Map.entry("ck_consent_revoked_after_granted", "UPDATE consent SET revoked_at = granted_at - interval '1 day'"),
            Map.entry("ck_consent_version_non_negative", "UPDATE consent SET version = -1"),
            Map.entry("ck_clarification_answer_answer_present",
                    "UPDATE clarification_answer SET free_text = NULL WHERE question_code = 'DEVICE_HARDWARE_OPENSSL'"),
            Map.entry("ck_clarification_answer_free_text_not_blank",
                    "UPDATE clarification_answer SET free_text = '  ' WHERE question_code = 'DEVICE_HARDWARE_OPENSSL'"),
            Map.entry("ck_scan_completed_matches_status", "UPDATE scan SET completed_at = started_at WHERE status = 'RUNNING'"),
            Map.entry("ck_scan_completed_after_started",
                    "UPDATE scan SET completed_at = started_at - interval '1 day' WHERE status = 'COMPLETED'"),
            Map.entry("ck_source_file_path_not_blank", "UPDATE source_file SET path = ' '"),
            Map.entry("ck_finding_key_size_positive", "UPDATE finding SET key_size_bits = 0"),
            Map.entry("ck_finding_lines_together", "UPDATE finding SET line_end = NULL"),
            Map.entry("ck_finding_line_start_positive", "UPDATE finding SET line_start = 0"),
            Map.entry("ck_finding_line_order", "UPDATE finding SET line_end = 9"),
            Map.entry("ck_finding_confidence_range", "UPDATE finding SET confidence = 1.5"),
            Map.entry("ck_finding_symbol_not_blank", "UPDATE finding SET symbol = ' '"),
            Map.entry("ck_scan_artifact_sha256_hex", "UPDATE scan_artifact SET sha256 = repeat('Z', 64)"),
            Map.entry("ck_scan_artifact_content_type_not_blank", "UPDATE scan_artifact SET content_type = ' '"),
            Map.entry("ck_service_node_name_not_blank", "UPDATE service_node SET name = ' ' WHERE name = 'gateway'"),
            Map.entry("ck_service_link_no_self_link", "UPDATE service_link SET target_node_id = source_node_id"),
            Map.entry("ck_service_link_mtls_needs_tls", "UPDATE service_link SET tls = false"),
            Map.entry("ck_link_call_site_line_start_positive", "UPDATE link_call_site SET line_start = 0"),
            Map.entry("ck_link_call_site_line_order", "UPDATE link_call_site SET line_end = 19"),
            Map.entry("ck_plan_item_risk_score_range", "UPDATE plan_item SET risk_score = 1.5"),
            Map.entry("ck_plan_item_version_non_negative", "UPDATE plan_item SET version = -1"),
            Map.entry("ck_plan_item_risk_factor_rank_positive", "UPDATE plan_item_risk_factor SET rank_no = 0"),
            Map.entry("ck_plan_item_risk_factor_feature_name_pattern", "UPDATE plan_item_risk_factor SET feature_name = 'Bad Name'"),
            Map.entry("ck_plan_item_state_transition_states_differ", "UPDATE plan_item_state_transition SET to_state = from_state"),
            Map.entry("ck_audit_log_project_key_hex", "UPDATE audit_log SET project_key = repeat('Z', 64)"),
            Map.entry("ck_audit_log_project_key_required", "UPDATE audit_log SET project_key = NULL"),
            Map.entry("ck_outbox_event_project_key_hex", "UPDATE outbox_event SET project_key = repeat('Z', 64)"),
            Map.entry("ck_outbox_event_schema_version_positive", "UPDATE outbox_event SET schema_version = 0"),
            Map.entry("ck_outbox_event_published_after_occurred", "UPDATE outbox_event SET published_at = occurred_at - interval '1 day'"),
            Map.entry("ck_idempotency_record_request_sha256_hex", "UPDATE idempotency_record SET request_sha256 = repeat('Z', 64)"),
            Map.entry("ck_idempotency_record_status_code_range", "UPDATE idempotency_record SET status_code = 600"),
            Map.entry("ck_idempotency_record_key_not_blank", "UPDATE idempotency_record SET idempotency_key = ' '"),
            Map.entry("ck_risk_class_threshold_min_score_range", "UPDATE risk_class_threshold SET min_score = 2 WHERE risk_class = 'LOW'"),
            Map.entry("ck_allowed_transition_states_differ",
                    "UPDATE allowed_transition SET to_state = from_state WHERE from_state = 'APPLIED' AND to_state = 'VERIFIED'"));

    /**
     * FOREIGN KEY violations where the generic statement could trip a second constraint first: the row is chosen (or
     * only one column changed) so that exactly the named key is broken.
     */
    private static final Map<String, String> FK_VIOLATIONS = Map.of(
            "fk_scan_status",
            "UPDATE scan SET status = 'NOPE' WHERE status = 'COMPLETED'",
            "fk_scan_project_id",
            "UPDATE scan SET project_id = gen_random_uuid() WHERE runtime_profile_sequence_no IS NULL",
            "fk_scan_project_id_runtime_profile_sequence_no",
            "UPDATE scan SET runtime_profile_sequence_no = 99 WHERE status = 'RUNNING'",
            "fk_project_runtime_profile_project_id",
            "UPDATE project_runtime_profile SET project_id = gen_random_uuid() WHERE sequence_no = 2",
            "fk_clarification_answer_question_code",
            "UPDATE clarification_answer SET question_code = 'NOPE' WHERE option_code IS NULL",
            "fk_clarification_answer_question_code_option_code",
            "UPDATE clarification_answer SET option_code = 'NOPE' WHERE question_code = 'TLS_TERMINATION'",
            "fk_allowed_transition_from_state",
            "UPDATE allowed_transition SET from_state = 'NOPE' WHERE from_state = 'APPLIED' AND to_state = 'VERIFIED'",
            "fk_allowed_transition_to_state",
            "UPDATE allowed_transition SET to_state = 'NOPE' WHERE from_state = 'APPLIED' AND to_state = 'VERIFIED'",
            "fk_clarification_option_question_code",
            "UPDATE clarification_option SET question_code = 'NOPE' WHERE question_code = 'JDK_UPGRADE_POSSIBLE' AND option_code = 'YES'");

    private record Constraint(String name, String table, char type, List<String> columns) {
    }

    private static JdbcClient app;
    private static List<Constraint> constraints;
    private static Map<String, Map<String, String>> columnTypes;
    private static Map<String, List<String>> primaryKeys;

    @BeforeAll
    static void loadFixture() {
        PostgresTestDatabase database = PostgresTestDatabase.get();
        database.truncate();
        app = JdbcClient.create(database.app());
        try (InputStream in = ConstraintCatalogTest.class.getResourceAsStream("/db/constraint-fixture.sql")) {
            String script = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            Arrays.stream(script.split(";\\s*\\n")).map(String::strip).filter(s -> !s.isEmpty())
                    .forEach(sql -> app.sql(sql).update());
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        JdbcClient catalog = JdbcClient.create(database.migrator());
        constraints = catalog.sql("""
                SELECT c.conname, t.relname, c.contype,
                       array_to_string(ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY AS k(num, ord)
                                             JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num
                                             ORDER BY k.ord), ',') AS cols
                FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public' AND c.contype IN ('c', 'u', 'f', 'p') AND t.relname <> 'flyway_schema_history'
                ORDER BY c.conname""")
                .query((rs, i) -> new Constraint(rs.getString(1), rs.getString(2), rs.getString(3).charAt(0),
                        List.of(rs.getString(4).split(","))))
                .list();
        columnTypes = new HashMap<>();
        catalog.sql("SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public'")
                .query(rs -> {
                    columnTypes.computeIfAbsent(rs.getString(1), k -> new HashMap<>()).put(rs.getString(2), rs.getString(3));
                });
        primaryKeys = constraints.stream().filter(c -> c.type() == 'p').collect(Collectors.toMap(Constraint::table, Constraint::columns));
    }

    @Test
    void catalogHasTheApprovedNumberOfConstraints() {
        Map<Character, Long> byType = constraints.stream().filter(c -> c.type() != 'p')
                .collect(Collectors.groupingBy(Constraint::type, Collectors.counting()));
        assertThat(byType).containsExactlyInAnyOrderEntriesOf(Map.of('c', 57L, 'f', 49L, 'u', 17L));
        assertThat(constraints.stream().filter(c -> c.type() == 'c' && !c.name().endsWith("_sort_order_positive")).map(Constraint::name))
                .containsExactlyInAnyOrderElementsOf(CHECK_VIOLATIONS.keySet());
    }

    @TestFactory
    Stream<DynamicTest> everyConstraintRejectsItsViolation() {
        List<DynamicTest> tests = new ArrayList<>();
        for (Constraint c : constraints) {
            if (c.type() != 'p') {
                tests.add(DynamicTest.dynamicTest(c.name(), () -> assertViolates(violation(c), c.name())));
            }
        }
        tests.add(DynamicTest.dynamicTest(PARTIAL_UNIQUE_INDEX, () -> assertViolates(copyRow("scan", Set.of(), "status = 'RUNNING'"),
                PARTIAL_UNIQUE_INDEX)));
        return tests.stream();
    }

    private static void assertViolates(String sql, String constraint) {
        Throwable failure = catchThrowable(() -> app.sql(sql).update());
        assertThat(failure).as(sql).isInstanceOf(DataAccessException.class);
        assertThat(SqlErrors.constraint(failure)).as(sql).contains(constraint);
    }

    private static String violation(Constraint c) {
        return switch (c.type()) {
            case 'c' -> c.name().endsWith("_sort_order_positive")
                    ? "UPDATE " + c.table() + " SET sort_order = 0 WHERE ctid = (SELECT ctid FROM " + c.table() + " LIMIT 1)"
                    : CHECK_VIOLATIONS.get(c.name());
            case 'f' -> FK_VIOLATIONS.getOrDefault(c.name(), danglingReference(c));
            case 'u' -> copyRow(c.table(), new HashSet<>(c.columns()), "true");
            default -> throw new IllegalStateException("unexpected constraint type " + c.type());
        };
    }

    /** Points every column of the foreign key at a parent that does not exist. */
    private static String danglingReference(Constraint fk) {
        String assignments = fk.columns().stream()
                .map(col -> col + " = " + missingValue(fk.table(), col))
                .collect(Collectors.joining(", "));
        return "UPDATE " + fk.table() + " SET " + assignments + " WHERE ctid = (SELECT ctid FROM " + fk.table() + " LIMIT 1)";
    }

    private static String missingValue(String table, String column) {
        String type = columnTypes.get(table).get(column);
        return switch (type) {
            case "uuid" -> "gen_random_uuid()";
            case "integer", "smallint" -> "999999";
            default -> "'NOPE_" + column.toUpperCase().substring(0, Math.min(column.length(), 20)) + "'";
        };
    }

    /**
     * Inserts a copy of one row that keeps the unique key and gives fresh values to the primary key and to the
     * columns of the table's other unique constraints.
     */
    private static String copyRow(String table, Set<String> keptKey, String where) {
        Set<String> fresh = new HashSet<>(primaryKeys.getOrDefault(table, List.of()));
        constraints.stream().filter(c -> c.type() == 'u' && c.table().equals(table)).forEach(c -> fresh.addAll(c.columns()));
        fresh.removeAll(keptKey);
        List<String> columns = new ArrayList<>(columnTypes.get(table).keySet());
        String select = columns.stream().map(col -> fresh.contains(col) ? freshValue(table, col) : col).collect(Collectors.joining(", "));
        return "INSERT INTO " + table + " (" + String.join(", ", columns) + ") SELECT " + select + " FROM " + table
                + " WHERE " + where + " LIMIT 1";
    }

    private static String freshValue(String table, String column) {
        String type = columnTypes.get(table).get(column);
        return switch (type) {
            case "uuid" -> "gen_random_uuid()";
            case "integer", "smallint" -> "777";
            default -> "'X' || substr(md5(random()::text), 1, 20)";
        };
    }
}
