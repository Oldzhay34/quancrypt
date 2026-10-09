package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.GetScanSummaryQuery;
import com.quancrypt.core.port.inbound.ListScansQuery;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.ScanSummaryView;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.port.outbound.IsolationLevel;
import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static com.quancrypt.core.fake.Problems.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

class ScanUseCasesTest {

    private final World w = new World();

    @Test
    void aScanStartsRunningWithTheCurrentRuntimeProfileSequence() {
        UUID projectId = w.project();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "25", Optional.empty(), Optional.empty(), "UI"));
        w.db.lockLog.clear();
        ScanView scan = w.startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI"));
        assertThat(scan.status()).isEqualTo("RUNNING");
        assertThat(scan.runtimeProfileSequenceNo()).hasValue(1);
        assertThat(scan.completedAt()).isEmpty();
        assertThat(w.db.lockLog).containsExactly("project:keyShare");
        assertThat(w.auditActions()).contains(AuditAction.SCAN_STARTED);
        assertThat(w.tx.isolations()).allMatch(level -> level == IsolationLevel.READ_COMMITTED);
    }

    @Test
    void aScanBeforeAnyRuntimeProfileHasNoSequence() {
        ScanView scan = w.startScan.execute(new StartScanCommand(w.project(), Optional.empty(), "UI"));
        assertThat(scan.runtimeProfileSequenceNo()).isEmpty();
    }

    @Test
    void onlyOneScanRunsPerProjectAndAnotherProjectIsNotAffected() {
        UUID projectId = w.project();
        UUID other = w.registerProject.execute(new RegisterProjectCommand("/other", "Other", Optional.empty(), "UI")).id();
        UUID first = w.runningScan(projectId);
        assertProblem(() -> w.startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI")), ProblemCode.SCAN_ALREADY_RUNNING);
        assertThat(w.startScan.execute(new StartScanCommand(other, Optional.empty(), "UI")).status()).isEqualTo("RUNNING");
        w.complete(first);
        assertThat(w.startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI")).status()).isEqualTo("RUNNING");
        assertProblem(() -> w.startScan.execute(new StartScanCommand(new UUID(9, 9), Optional.empty(), "UI")), ProblemCode.NOT_FOUND);
    }

    @Test
    void startingWithTheSameIdempotencyKeyReturnsTheSameScan() {
        UUID projectId = w.project();
        StartScanCommand command = new StartScanCommand(projectId, World.idem("s1", "digest"), "UI");
        ScanView first = w.startScan.execute(command);
        ScanView replay = w.startScan.execute(command);
        assertThat(replay.id()).isEqualTo(first.id());
        assertThat(w.db.scans).hasSize(1);
        assertProblem(() -> w.startScan.execute(new StartScanCommand(projectId, World.idem("s1", "another"), "UI")), ProblemCode.IDEMPOTENCY_CONFLICT);
    }

    @Test
    void scansAreListedNewestFirst() {
        UUID projectId = w.project();
        UUID first = w.runningScan(projectId);
        w.complete(first);
        UUID second = w.runningScan(projectId);
        PageView<ScanView> page = w.listScans.execute(new ListScansQuery(projectId, 0, 10));
        assertThat(page.items()).extracting(ScanView::id).containsExactly(second, first);
        assertProblem(() -> w.listScans.execute(new ListScansQuery(new UUID(9, 9), 0, 10)), ProblemCode.NOT_FOUND);
        assertProblem(() -> w.listScans.execute(new ListScansQuery(projectId, 0, 500)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void completingWithConsentWritesAScanCompletedEventWithCountsAndVersions() {
        UUID projectId = w.projectWithWarehouseConsent();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "25.0.4.1", Optional.of("4.1.1"), Optional.empty(), "UI"));
        UUID scanId = w.runningScan(projectId);
        w.record(scanId, World.tlsFinding("src/A.java", "A#connect"), World.finding("src/B.java", "B#sign", "SHA1", "SIGNATURE", "CODE", "P0", null));
        w.clock.advance(Duration.ofSeconds(42));
        w.db.lockLog.clear();
        ScanView done = w.complete(scanId);
        assertThat(done.status()).isEqualTo("COMPLETED");
        assertThat(done.completedAt()).isPresent();
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share");
        OutboxRecord event = w.outbox().stream().filter(r -> r.type() == EventType.SCAN_COMPLETED).findFirst().orElseThrow();
        assertThat(event.payload()).containsEntry("finding_count", 2).containsEntry("java_version", "25.0.4.1")
                .containsEntry("spring_boot_version", "4.1.1").containsEntry("duration_seconds", 42L);
        assertThat(event.payload().get("priority_counts")).isEqualTo(Map.of("P0", 1, "P1", 1));
        assertThat(w.auditActions()).contains(AuditAction.SCAN_COMPLETED);
    }

    @Test
    void aFailedScanWritesNoEventAndCompletingWithoutConsentWritesNone() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        ScanView failed = w.completeScan.execute(new CompleteScanCommand(scanId, "FAILED", Optional.empty(), "UI"));
        assertThat(failed.status()).isEqualTo("FAILED");
        assertThat(w.outbox()).isEmpty();
        UUID noConsent = w.registerProject.execute(new RegisterProjectCommand("/other", "Other", Optional.empty(), "UI")).id();
        w.complete(w.runningScan(noConsent));
        assertThat(w.outbox()).isEmpty();
    }

    @Test
    void completingTwiceWithTheSameOutcomeIsIdempotentAndAnotherOutcomeIsAnError() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        w.complete(scanId);
        int events = w.outbox().size();
        int audits = w.db.audit.size();
        assertThat(w.complete(scanId).status()).isEqualTo("COMPLETED");
        assertThat(w.outbox()).hasSize(events);
        assertThat(w.db.audit).hasSize(audits);
        assertProblem(() -> w.completeScan.execute(new CompleteScanCommand(scanId, "FAILED", Optional.empty(), "UI")), ProblemCode.SCAN_NOT_RUNNING);
    }

    @Test
    void invalidOutcomesAndUnknownScansAreRejected() {
        UUID scanId = w.runningScan(w.project());
        assertProblem(() -> w.completeScan.execute(new CompleteScanCommand(scanId, "RUNNING", Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.completeScan.execute(new CompleteScanCommand(scanId, "DONE", Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.completeScan.execute(new CompleteScanCommand(new UUID(9, 9), "COMPLETED", Optional.empty(), "UI")), ProblemCode.NOT_FOUND);
    }

    @Test
    void aCompletionRetryWithTheSameIdempotencyKeyReplays() {
        UUID scanId = w.runningScan(w.project());
        CompleteScanCommand command = new CompleteScanCommand(scanId, "COMPLETED", World.idem("c1", "d"), "UI");
        ScanView first = w.completeScan.execute(command);
        assertThat(w.completeScan.execute(command).completedAt()).isEqualTo(first.completedAt());
    }

    @Test
    void theSummaryCountsFindingsByPriorityAlgorithmAndKind() {
        UUID projectId = w.project();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "25", Optional.empty(), Optional.empty(), "UI"));
        UUID scanId = w.runningScan(projectId);
        w.record(scanId, World.tlsFinding("src/A.java", "A#one"), World.tlsFinding("src/A.java", "A#two"),
                World.finding("certs/ca.pem", "ca.pem", "RSA", "CERTIFICATE", "CERTIFICATE_FILE", "P3", 2048));
        ScanSummaryView summary = w.getScanSummary.execute(new GetScanSummaryQuery(scanId));
        assertThat(summary.findingCount()).isEqualTo(3);
        assertThat(summary.countsByPriority()).containsEntry("P1", 2).containsEntry("P3", 1);
        assertThat(summary.countsByAlgorithmFamily()).containsEntry("RSA", 3);
        assertThat(summary.countsByLocationKind()).containsEntry("CODE", 2).containsEntry("CERTIFICATE_FILE", 1);
        assertThat(summary.runtimeProfile()).hasValueSatisfying(p -> assertThat(p.javaVersion()).isEqualTo("25"));
        assertProblem(() -> w.getScanSummary.execute(new GetScanSummaryQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
    }
}
