package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.ClarificationAnswerInput;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordScanArtifactCommand;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersCommand;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * acid-3nf-database section 7, KVKK deletion (D-127): deleting a project removes every row of its tree; the audit log
 * and already sent outbox events stay, pending events are dropped and one consent_revoked per consent type is written.
 */
class KvkkDeleteTest extends IntegrationTest {

    private static final List<String> PROJECT_TREE = List.of(
            "project", "project_runtime_profile", "consent", "clarification_answer", "scan", "source_file", "finding", "scan_artifact",
            "topology", "service_node", "service_link", "link_call_site", "link_finding", "plan", "plan_item", "plan_item_risk_factor",
            "plan_item_state_transition");

    @Test
    void deletingAProjectRemovesItsTreeAndKeepsTheAuditTrail() {
        UUID projectId = projectWithConsent("/work/demo");
        grantConsent.execute(new GrantConsentCommand(projectId, "MODEL_TRAINING", 1, Optional.empty(), Optional.empty(), "UI"));
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.empty(), Optional.empty(), "UI"));
        relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));
        saveClarificationAnswers.execute(new SaveClarificationAnswersCommand(projectId,
                List.of(new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty())), "UI"));
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();
        recordTopology.execute(new RecordTopologyCommand(scanId, List.of(new NodeInput("gateway", "GATEWAY"), new NodeInput("account", "SERVICE")),
                List.of(new LinkInput("gateway", "account", "HTTP", true, true,
                        List.of(new CallSiteInput("src/main/java/Client.java", 5, 6, "CODE")), ids)), "UI"));
        recordScanArtifact.execute(new RecordScanArtifactCommand(scanId, "application/json", "{}".getBytes(StandardCharsets.UTF_8), "UI"));
        complete(scanId);
        plan(scanId, ids);
        String projectKey = jdbc.sql("SELECT project_key FROM project").query(String.class).single();
        long auditBefore = rows("audit_log");
        long published = jdbc.sql("SELECT count(*) FROM outbox_event WHERE published_at IS NOT NULL").query(Long.class).single();
        PROJECT_TREE.forEach(table -> assertThat(rows(table)).as(table).isPositive());

        deleteProject.execute(new DeleteProjectCommand(projectId, "UI"));

        PROJECT_TREE.forEach(table -> assertThat(rows(table)).as(table).isZero());
        assertThat(rows("audit_log")).isEqualTo(auditBefore + 1);
        assertThat(jdbc.sql("SELECT action_code FROM audit_log ORDER BY occurred_at DESC, id DESC LIMIT 1").query(String.class).single())
                .isEqualTo("PROJECT_DELETED");
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE published_at IS NOT NULL").query(Long.class).single()).isEqualTo(published);
        assertThat(jdbc.sql("""
                SELECT payload->>'consent_type' FROM outbox_event
                WHERE project_key = :key AND published_at IS NULL ORDER BY payload->>'consent_type'""")
                .param("key", projectKey).query(String.class).list())
                .containsExactly("MODEL_TRAINING", "WAREHOUSE_ANALYTICS");
        assertThat(jdbc.sql("""
                SELECT bool_and(event_type = 'consent_revoked' AND (payload->>'delete_requested')::boolean)
                FROM outbox_event WHERE project_key = :key AND published_at IS NULL""")
                .param("key", projectKey).query(Boolean.class).single()).isTrue();
    }
}
