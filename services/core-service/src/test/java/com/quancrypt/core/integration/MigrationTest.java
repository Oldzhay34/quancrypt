package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * acid-3nf-database section 7, migration test: on an empty database the three migrations build exactly the approved
 * G-CORE-DB schema (43 tables, 3 views, the indexes) and its lookup data, and the service role gets DML only (D-54).
 */
class MigrationTest {

    private static final List<String> TABLES = List.of(
            "algorithm_family", "allowed_transition", "answer_kind", "audit_action", "audit_log", "caller_kind", "clarification_answer",
            "clarification_option", "clarification_question", "classified_by", "consent", "consent_type", "effort_level", "event_type",
            "finding", "idempotency_record", "link_call_site", "link_finding", "location_kind", "node_kind", "outbox_event", "plan",
            "plan_item", "plan_item_risk_factor", "plan_item_state", "plan_item_state_transition", "priority", "privacy_notice", "project",
            "project_runtime_profile", "protocol", "quantum_status", "risk_class", "risk_class_threshold", "scan", "scan_artifact",
            "scan_status", "service_link", "service_node", "source_file", "strategy", "topology", "usage_context");

    private static final List<String> INDEXES = List.of(
            "ix_audit_log_project_key_occurred_at", "ix_consent_privacy_notice_id", "ix_idempotency_record_created_at",
            "ix_link_call_site_source_file_id", "ix_link_finding_finding_id", "ix_outbox_event_pending", "ix_outbox_event_project_key",
            "ix_plan_item_plan_id_state", "ix_plan_item_state_transition_plan_item_id_transitioned_at",
            "ix_scan_project_id_runtime_profile_sequence_no", "ix_service_link_target_node_id", "uq_scan_one_running_per_project");

    private final JdbcClient migrator = JdbcClient.create(PostgresTestDatabase.get().migrator());
    private final JdbcClient app = JdbcClient.create(PostgresTestDatabase.get().app());

    @Test
    void migrationsBuildTheApprovedTablesViewsAndIndexes() {
        assertThat(migrator.sql("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE' AND table_name <> 'flyway_schema_history'
                ORDER BY table_name""").query(String.class).list()).containsExactlyElementsOf(TABLES);
        assertThat(migrator.sql("SELECT table_name FROM information_schema.views WHERE table_schema = 'public' ORDER BY table_name")
                .query(String.class).list())
                .containsExactly("v_finding_call_site_count", "v_plan_item_risk", "v_project_current_runtime");
        assertThat(migrator.sql("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public' AND tablename <> 'flyway_schema_history'
                  AND (starts_with(indexname, 'ix_') OR indexname = 'uq_scan_one_running_per_project')
                ORDER BY indexname""").query(String.class).list()).containsExactlyElementsOf(INDEXES);
        assertThat(migrator.sql("SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank").query(String.class).list())
                .containsExactly("1", "2", "3");
    }

    @Test
    void lookupDataAndPrivacyNoticeAreSeeded() {
        Map<String, Integer> expected = Map.ofEntries(
                Map.entry("quantum_status", 3), Map.entry("algorithm_family", 21), Map.entry("usage_context", 13), Map.entry("location_kind", 6),
                Map.entry("priority", 4), Map.entry("effort_level", 3), Map.entry("strategy", 8), Map.entry("risk_class", 4),
                Map.entry("risk_class_threshold", 4), Map.entry("plan_item_state", 6), Map.entry("allowed_transition", 6),
                Map.entry("scan_status", 3), Map.entry("node_kind", 5), Map.entry("protocol", 6), Map.entry("consent_type", 2),
                Map.entry("classified_by", 2), Map.entry("caller_kind", 2), Map.entry("answer_kind", 3), Map.entry("event_type", 7),
                Map.entry("audit_action", 14), Map.entry("clarification_question", 5), Map.entry("clarification_option", 14),
                Map.entry("privacy_notice", 1));
        expected.forEach((table, count) ->
                assertThat(migrator.sql("SELECT count(*) FROM " + table).query(Integer.class).single()).as(table).isEqualTo(count));
        assertThat(migrator.sql("SELECT text_tr <> '' AND text_en <> '' FROM privacy_notice WHERE version = 1").query(Boolean.class).single())
                .isTrue();
    }

    @Test
    void theServiceRoleHasDmlButNoDdl() {
        Throwable ddl = catchThrowable(() -> app.sql("CREATE TABLE intruder (id int)").update());
        Throwable dropColumn = catchThrowable(() -> app.sql("ALTER TABLE project DROP COLUMN display_name").update());

        assertThat(SqlErrors.sqlState(ddl)).contains("42501");
        assertThat(SqlErrors.sqlState(dropColumn)).contains("42501");
        assertThat(app.sql("SELECT count(*) FROM v_plan_item_risk").query(Integer.class).single()).isNotNegative();
    }
}
