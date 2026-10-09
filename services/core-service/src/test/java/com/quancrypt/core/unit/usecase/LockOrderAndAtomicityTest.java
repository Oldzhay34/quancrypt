package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.fake.InMemoryDatabase;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.ClarificationAnswerInput;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
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
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LockOrderAndAtomicityTest {

    private final World w = new World();

    @Test
    void theEventWritingUseCasesTakeTheirRowLocksInTheBindingOrderProjectThenConsentThenScan() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        List<List<String>> orders = new ArrayList<>();

        w.db.lockLog.clear();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "25", Optional.empty(), Optional.empty(), "UI"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:noKeyUpdate", "consent:share");

        w.db.lockLog.clear();
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:noKeyUpdate");

        w.db.lockLog.clear();
        w.recordScanArtifact.execute(new RecordScanArtifactCommand(scanId, "application/json", new byte[] {1}, "INTERNAL"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:noKeyUpdate");

        w.db.lockLog.clear();
        w.recordTopology.execute(new RecordTopologyCommand(scanId, List.of(new NodeInput("a", "SERVICE")), List.of(), "INTERNAL"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:noKeyUpdate");

        w.db.lockLog.clear();
        w.saveClarificationAnswers.execute(new SaveClarificationAnswersCommand(projectId,
                List.of(new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty())), "UI"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare");

        w.db.lockLog.clear();
        w.complete(scanId);
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share");

        w.db.lockLog.clear();
        w.plan(scanId, 0.5);
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:share");

        w.db.lockLog.clear();
        UUID itemId = w.db.planItems.keySet().iterator().next();
        w.transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, Optional.empty(), "UI"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share");

        w.db.lockLog.clear();
        w.revokeConsent.execute(new RevokeConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 0, "UI"));
        orders.add(List.copyOf(w.db.lockLog));
        assertThat(w.db.lockLog).containsExactly("project:keyShare");

        assertThat(orders).allSatisfy(order -> assertThat(order.get(0)).startsWith("project:"));
    }

    private List<String> locksOf(Runnable useCase) {
        w.db.lockLog.clear();
        useCase.run();
        return List.copyOf(w.db.lockLog);
    }

    @Test
    void theIdempotencyRecordIsTheFirstLockOfEveryCommandThatCarriesAKey() {
        assertThat(locksOf(() -> w.registerProject.execute(new RegisterProjectCommand("/a", "A", Optional.of("r1"), "UI"))))
                .containsExactly("idempotency:begin");
        UUID projectId = w.projectWithWarehouseConsent();
        assertThat(locksOf(() -> w.startScan.execute(new StartScanCommand(projectId, World.idem("s1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:keyShare");
        UUID scanId = w.db.scans.keySet().iterator().next();
        assertThat(locksOf(() -> w.grantConsent.execute(new GrantConsentCommand(projectId, "MODEL_TRAINING", 1, Optional.empty(), World.idem("g1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:keyShare");
        assertThat(locksOf(() -> w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "25", Optional.empty(), World.idem("p1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:noKeyUpdate", "consent:share");
        assertThat(locksOf(() -> w.recordFindings.execute(new RecordFindingsCommand(scanId, List.of(World.tlsFinding("src/A.java", "A#x")), World.idem("f1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:keyShare", "consent:share", "scan:noKeyUpdate");
        assertThat(locksOf(() -> w.completeScan.execute(new CompleteScanCommand(scanId, "COMPLETED", World.idem("c1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:keyShare", "consent:share");
        assertThat(locksOf(() -> w.createPlan.execute(new CreatePlanCommand(scanId, w.assessAll(scanId, 0.5), World.idem("cp1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:keyShare", "consent:share", "scan:share");
        UUID itemId = w.db.planItems.keySet().iterator().next();
        assertThat(locksOf(() -> w.transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, World.idem("t1", "d"), "UI"))))
                .containsExactly("idempotency:begin", "project:keyShare", "consent:share");
        assertThat(locksOf(() -> w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(10)))).isEmpty();
    }

    @Test
    void aFailureAfterTheWritesRollsEverythingBack() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        InMemoryDatabase.Snapshot before = w.db.snapshot();

        w.auditLog.failNextAppend();
        assertThatThrownBy(() -> w.recordFindings.execute(new RecordFindingsCommand(scanId, List.of(World.tlsFinding("src/A.java", "A#x")), World.idem("k", "d"), "UI")))
                .isInstanceOf(IllegalStateException.class);
        assertThat(w.db.snapshot()).isEqualTo(before);
        assertThat(w.db.findings).isEmpty();
        assertThat(w.db.sourceFiles).isEmpty();
        assertThat(w.outbox()).isEmpty();
        assertThat(w.db.idempotency).isEmpty();

        w.auditLog.failNextAppend();
        assertThatThrownBy(() -> w.deleteProject.execute(new DeleteProjectCommand(projectId, "UI"))).isInstanceOf(IllegalStateException.class);
        assertThat(w.db.snapshot()).isEqualTo(before);
        assertThat(w.db.projects).hasSize(1);
        assertThat(w.db.scans).hasSize(1);
        assertThat(w.outbox()).isEmpty();

        w.auditLog.failNextAppend();
        assertThatThrownBy(() -> w.revokeConsent.execute(new RevokeConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 0, "UI")))
                .isInstanceOf(IllegalStateException.class);
        assertThat(w.db.snapshot()).isEqualTo(before);
        assertThat(w.db.consents.values()).allSatisfy(c -> assertThat(c.isActive()).isTrue());
    }

    @Test
    void aFailedPlanLeavesNoPlanItemsTransitionsOrEvents() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        w.complete(scanId);
        InMemoryDatabase.Snapshot before = w.db.snapshot();
        w.auditLog.failNextAppend();
        assertThatThrownBy(() -> w.plan(scanId, 0.5)).isInstanceOf(IllegalStateException.class);
        assertThat(w.db.snapshot()).isEqualTo(before);
        assertThat(w.db.plans).isEmpty();
        assertThat(w.db.planItems).isEmpty();
        assertThat(w.db.transitions).isEmpty();
        assertThat(w.plan(scanId, 0.5).itemCount()).isEqualTo(1);
    }

    @Test
    void aFailedTransitionLeavesTheItemAtItsOldStateAndVersion() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        w.complete(scanId);
        w.plan(scanId, 0.5);
        PlanItem item = w.db.planItems.values().iterator().next();
        InMemoryDatabase.Snapshot before = w.db.snapshot();
        w.auditLog.failNextAppend();
        assertThatThrownBy(() -> w.transitionPlanItem.execute(new TransitionPlanItemCommand(item.id(), "APPROVED", 1, Optional.empty(), "UI")))
                .isInstanceOf(IllegalStateException.class);
        assertThat(w.db.snapshot()).isEqualTo(before);
        assertThat(w.db.planItems.get(item.id()).version()).isEqualTo(1);
    }
}
