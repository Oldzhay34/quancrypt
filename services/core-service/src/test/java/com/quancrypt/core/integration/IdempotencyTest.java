package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.fake.Problems;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.inbound.view.ProjectView;
import com.quancrypt.core.port.inbound.view.RecordFindingsResult;
import com.quancrypt.core.port.inbound.view.ScanView;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * acid-3nf-database section 7, idempotency (D-144): the same Idempotency-Key with the same request creates one record and
 * replays its result; the same key with another request is 409 idempotency-conflict.
 */
class IdempotencyTest extends IntegrationTest {

    private static final String DIGEST = "1".repeat(64);
    private static final String OTHER = "2".repeat(64);

    @Test
    void registerProjectReplaysAndConflicts() {
        ProjectView first = registerProject.execute(new RegisterProjectCommand("/work/demo", "Demo", Optional.of("k1"), "UI"));
        ProjectView again = registerProject.execute(new RegisterProjectCommand("/work/demo", "Demo", Optional.of("k1"), "UI"));

        assertThat(again.id()).isEqualTo(first.id());
        assertThat(rows("project")).isEqualTo(1);
        assertThat(rows("idempotency_record")).isEqualTo(1);
        Problems.assertProblem(() -> registerProject.execute(new RegisterProjectCommand("/work/other", "Other", Optional.of("k1"), "UI")),
                ProblemCode.IDEMPOTENCY_CONFLICT);
    }

    @Test
    void startScanReplaysTheSameScan() {
        UUID projectId = project("/work/demo");
        ScanView first = startScan.execute(new StartScanCommand(projectId, idem("k1", DIGEST), "UI"));
        ScanView again = startScan.execute(new StartScanCommand(projectId, idem("k1", DIGEST), "UI"));

        assertThat(again.id()).isEqualTo(first.id());
        assertThat(rows("scan")).isEqualTo(1);
        Problems.assertProblem(() -> startScan.execute(new StartScanCommand(projectId, idem("k1", OTHER), "UI")), ProblemCode.IDEMPOTENCY_CONFLICT);
    }

    @Test
    void recordFindingsReplayCreatesNothing() {
        UUID scanId = runningScan(projectWithConsent("/work/demo"));
        RecordFindingsCommand command = new RecordFindingsCommand(scanId, List.of(tlsFinding("src/main/java/Tls.java", "Tls#a")),
                idem("k1", DIGEST), "UI");

        RecordFindingsResult first = recordFindings.execute(command);
        RecordFindingsResult again = recordFindings.execute(command);

        assertThat(first.createdCount()).isEqualTo(1);
        assertThat(again.createdCount()).isZero();
        assertThat(again.createdIds()).isEmpty();
        assertThat(rows("finding")).isEqualTo(1);
        assertThat(rows("outbox_event")).isEqualTo(1);
    }

    @Test
    void completeScanCreatePlanAndTransitionReplay() {
        UUID scanId = runningScan(projectWithConsent("/work/demo"));
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();

        completeScan.execute(new CompleteScanCommand(scanId, "COMPLETED", idem("k-done", DIGEST), "UI"));
        completeScan.execute(new CompleteScanCommand(scanId, "COMPLETED", idem("k-done", DIGEST), "UI"));
        PlanView plan = createPlan.execute(new CreatePlanCommand(scanId, assessAll(ids), idem("k-plan", DIGEST), "UI"));
        PlanView planAgain = createPlan.execute(new CreatePlanCommand(scanId, assessAll(ids), idem("k-plan", DIGEST), "UI"));
        UUID itemId = jdbc.sql("SELECT id FROM plan_item").query(UUID.class).single();
        transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, idem("k-tr", DIGEST), "UI"));
        transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, idem("k-tr", DIGEST), "UI"));

        assertThat(planAgain.id()).isEqualTo(plan.id());
        assertThat(rows("plan")).isEqualTo(1);
        assertThat(jdbc.sql("SELECT version FROM plan_item").query(Integer.class).single()).isEqualTo(2);
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'scan_completed'").query(Integer.class).single()).isEqualTo(1);
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'plan_item_transitioned'").query(Integer.class).single())
                .isEqualTo(1);
        Problems.assertProblem(() -> transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPLIED", 2, idem("k-tr", OTHER), "UI")),
                ProblemCode.IDEMPOTENCY_CONFLICT);
    }
}
