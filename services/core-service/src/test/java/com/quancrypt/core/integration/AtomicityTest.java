package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.ClarificationAnswerInput;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordScanArtifactCommand;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.RevokeConsentCommand;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersCommand;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * acid-3nf-database section 7, atomicity: each of the 14 write use cases fails at its last step (the audit entry) and
 * leaves no trace: no state change, no outbox event, no idempotency record, no audit entry.
 */
class AtomicityTest extends IntegrationTest {

    private static final String DIGEST = "d".repeat(64);

    private static final List<String> TABLES = List.of(
            "project", "project_runtime_profile", "consent", "clarification_answer", "scan", "source_file", "finding", "scan_artifact",
            "topology", "service_node", "service_link", "link_call_site", "link_finding", "plan", "plan_item", "plan_item_risk_factor",
            "plan_item_state_transition", "audit_log", "outbox_event", "idempotency_record");

    private static Map<String, Long> snapshot() {
        Map<String, Long> counts = new LinkedHashMap<>();
        TABLES.forEach(t -> counts.put(t, rows(t)));
        counts.put("published", JdbcCounts.published());
        counts.put("revoked", JdbcCounts.revokedConsents());
        counts.put("running", JdbcCounts.runningScans());
        counts.put("approved", JdbcCounts.approvedItems());
        return counts;
    }

    private void assertNoTrace(Runnable failingCall) {
        Map<String, Long> before = snapshot();
        auditFailure.failNextAppend();
        assertThatThrownBy(failingCall::run).hasMessageContaining("injected audit failure");
        assertThat(snapshot()).isEqualTo(before);
    }

    @Test
    void projectUseCasesRollBack() {
        assertNoTrace(() -> registerProject.execute(new RegisterProjectCommand("/work/new", "New", Optional.of("k-reg"), "UI")));
        UUID projectId = projectWithConsent("/work/demo");
        assertNoTrace(() -> recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.of("4.1.1"),
                idem("k-prof", DIGEST), "UI")));
        // A pending event the deletion would drop (D-127): after the failed deletion it must still be there.
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.empty(), Optional.empty(), "UI"));
        assertThat(rows("outbox_event")).isEqualTo(1);
        assertNoTrace(() -> deleteProject.execute(new DeleteProjectCommand(projectId, "UI")));
        assertThat(jdbc.sql("SELECT event_type FROM outbox_event").query(String.class).list()).containsExactly("project_runtime_changed");
        assertNoTrace(() -> saveClarificationAnswers.execute(new SaveClarificationAnswersCommand(projectId,
                List.of(new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty())), "UI")));
    }

    @Test
    void consentUseCasesRollBack() {
        UUID projectId = project("/work/demo");
        assertNoTrace(() -> grantConsent.execute(new GrantConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 2, Optional.empty(),
                idem("k-grant", DIGEST), "UI")));
        grantConsent.execute(new GrantConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 2, Optional.empty(), Optional.empty(), "UI"));
        assertNoTrace(() -> revokeConsent.execute(new RevokeConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 0, "UI")));
    }

    @Test
    void scanUseCasesRollBack() {
        UUID projectId = projectWithConsent("/work/demo");
        assertNoTrace(() -> startScan.execute(new StartScanCommand(projectId, idem("k-start", DIGEST), "UI")));
        UUID scanId = runningScan(projectId);
        assertNoTrace(() -> recordFindings.execute(new RecordFindingsCommand(scanId,
                List.of(tlsFinding("src/main/java/Tls.java", "Tls#a")), idem("k-find", DIGEST), "UI")));
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();
        assertNoTrace(() -> recordTopology.execute(new RecordTopologyCommand(scanId,
                List.of(new NodeInput("gateway", "GATEWAY"), new NodeInput("account", "SERVICE")),
                List.of(new LinkInput("gateway", "account", "HTTP", true, true,
                        List.of(new CallSiteInput("src/main/java/Client.java", 5, 6, "CODE")), ids)), "UI")));
        assertNoTrace(() -> recordScanArtifact.execute(new RecordScanArtifactCommand(scanId, "application/json",
                "{}".getBytes(StandardCharsets.UTF_8), "UI")));
        assertNoTrace(() -> completeScan.execute(new CompleteScanCommand(scanId, "COMPLETED", idem("k-done", DIGEST), "UI")));
    }

    @Test
    void planUseCasesRollBack() {
        UUID projectId = projectWithConsent("/work/demo");
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();
        complete(scanId);
        assertNoTrace(() -> createPlan.execute(new CreatePlanCommand(scanId, assessAll(ids), idem("k-plan", DIGEST), "UI")));
        plan(scanId, ids);
        UUID itemId = jdbc.sql("SELECT id FROM plan_item").query(UUID.class).single();
        assertNoTrace(() -> transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, idem("k-tr", DIGEST), "UI")));
    }

    @Test
    void relayRollsBackMarksWhenItsAuditFails() {
        projectWithConsent("/work/demo");
        UUID projectId = jdbc.sql("SELECT id FROM project").query(UUID.class).single();
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.empty(), Optional.empty(), "UI"));
        assertThat(rows("outbox_event")).isEqualTo(1);

        assertNoTrace(() -> relayOutboxEvents.execute(new RelayOutboxEventsCommand(100)));
    }

    /** Counts of state changes that keep the row count (updates), read as the migrator. */
    private static final class JdbcCounts {

        private static long count(String sql) {
            return JdbcClient.create(PostgresTestDatabase.get().migrator()).sql(sql).query(Long.class).single();
        }

        static long published() {
            return count("SELECT count(*) FROM outbox_event WHERE published_at IS NOT NULL");
        }

        static long revokedConsents() {
            return count("SELECT count(*) FROM consent WHERE revoked_at IS NOT NULL");
        }

        static long runningScans() {
            return count("SELECT count(*) FROM scan WHERE status = 'RUNNING'");
        }

        static long approvedItems() {
            return count("SELECT count(*) FROM plan_item WHERE state <> 'PLANNED'");
        }
    }
}
