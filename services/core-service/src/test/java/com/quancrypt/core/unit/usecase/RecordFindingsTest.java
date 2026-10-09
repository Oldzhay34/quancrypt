package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.FindingInput;
import com.quancrypt.core.port.inbound.GetFindingQuery;
import com.quancrypt.core.port.inbound.ListFindingsQuery;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.view.FindingView;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.RecordFindingsResult;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

import static com.quancrypt.core.fake.Problems.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

class RecordFindingsTest {

    private final World w = new World();

    private UUID consentedScan() {
        return w.runningScan(w.projectWithWarehouseConsent());
    }

    @Test
    void findingsAreStoredWithTheirFilesAndOneEventEachWhenConsentExists() {
        UUID scanId = consentedScan();
        w.db.lockLog.clear();
        RecordFindingsResult result = w.record(scanId, World.tlsFinding("src/A.java", "A#one"), World.tlsFinding("src/A.java", "A#two"),
                World.finding("src/B.java", "B#sign", "SHA1", "SIGNATURE", "CODE", "P0", null));
        assertThat(result.createdCount()).isEqualTo(3);
        assertThat(result.existingCount()).isZero();
        assertThat(result.createdIds()).hasSize(3);
        assertThat(w.db.sourceFiles).hasSize(2);
        assertThat(w.db.findings).hasSize(3);
        assertThat(w.outboxTypes()).containsExactly(EventType.FINDING_DETECTED, EventType.FINDING_DETECTED, EventType.FINDING_DETECTED);
        assertThat(w.outbox().get(0).payload()).containsEntry("algorithm_family", "RSA").containsEntry("location_kind", "CODE")
                .containsEntry("priority", "P1").containsEntry("classified_by", "STATIC");
        assertThat(w.auditActions()).contains(AuditAction.FINDINGS_RECORDED);
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:noKeyUpdate");
    }

    @Test
    void withoutConsentNoEventIsWrittenButTheAuditRowIs() {
        UUID scanId = w.runningScan(w.project());
        w.record(scanId, World.tlsFinding("src/A.java", "A#one"));
        assertThat(w.outbox()).isEmpty();
        assertThat(w.auditActions()).contains(AuditAction.FINDINGS_RECORDED);
    }

    @Test
    void aRepeatedFindingIsCountedAsExistingAndWritesNoSecondEvent() {
        UUID scanId = consentedScan();
        w.record(scanId, World.tlsFinding("src/A.java", "A#one"));
        RecordFindingsResult again = w.record(scanId, World.tlsFinding("src/A.java", "A#one"), World.tlsFinding("src/A.java", "A#two"));
        assertThat(again.createdCount()).isEqualTo(1);
        assertThat(again.existingCount()).isEqualTo(1);
        assertThat(w.outbox()).hasSize(2);
        assertThat(w.db.findings).hasSize(2);
    }

    @Test
    void aPriorityThatContradictsTheTableIsRejectedAndNothingIsStored() {
        UUID scanId = consentedScan();
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#x", "RSA", "TLS_KEY_EXCHANGE", "CODE", "P3", 2048)), ProblemCode.VALIDATION_FAILED);
        assertThat(w.db.sourceFiles).isEmpty();
        assertThat(w.db.findings).isEmpty();
    }

    @Test
    void findingsThatNeedNoMigrationAreRejected() {
        UUID scanId = consentedScan();
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#x", "AES", "ENCRYPTION", "CODE", "P3", 256)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#x", "SHA2", "HASH", "CODE", "P3", null)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#x", "ML_KEM", "TLS_KEY_EXCHANGE", "CONFIG", "P1", null)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void p0IsAcceptedForAesBecauseOfTheEcbMode() {
        UUID scanId = consentedScan();
        assertThat(w.record(scanId, World.finding("src/A.java", "A#ecb", "AES", "ENCRYPTION", "CODE", "P0", 128)).createdCount()).isEqualTo(1);
        assertThat(w.db.findings.values().iterator().next().priority()).isEqualTo(Priority.P0);
    }

    @Test
    void anUnknownAlgorithmKeepsTheSuppliedPriorityWhenAStrategyCanPlanIt() {
        UUID scanId = consentedScan();
        assertThat(w.record(scanId, World.finding("src/A.java", "A#tls", "UNKNOWN", "TLS_KEY_EXCHANGE", "CODE", "P1", null)).createdCount()).isEqualTo(1);
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#odd", "UNKNOWN", "UNKNOWN", "CODE", "P2", null)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aScanThatIsNotRunningOrDoesNotExistRejectsFindings() {
        UUID scanId = consentedScan();
        w.complete(scanId);
        assertProblem(() -> w.record(scanId, World.tlsFinding("src/A.java", "A#x")), ProblemCode.SCAN_NOT_RUNNING);
        assertProblem(() -> w.record(new UUID(9, 9), World.tlsFinding("src/A.java", "A#x")), ProblemCode.NOT_FOUND);
    }

    @Test
    void batchSizeAndFieldsAreValidated() {
        UUID scanId = consentedScan();
        assertProblem(() -> w.recordFindings.execute(new RecordFindingsCommand(scanId, List.of(), Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        List<FindingInput> tooMany = IntStream.range(0, 501).mapToObj(i -> World.tlsFinding("src/A.java", "A#" + i)).toList();
        assertProblem(() -> w.recordFindings.execute(new RecordFindingsCommand(scanId, tooMany, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#x", "ROT13", "TLS_KEY_EXCHANGE", "CODE", "P1", null)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.record(scanId, World.tlsFinding(" ", "A#x")), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.record(scanId, new FindingInput("src/A.java", "A#x", "RSA", "TLS_KEY_EXCHANGE", "CODE", "P1", Optional.of(2048),
                Optional.of(10), Optional.of(5), 0.9, "STATIC")), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.record(scanId, new FindingInput("src/A.java", "A#x", "RSA", "TLS_KEY_EXCHANGE", "CODE", "P1", Optional.of(2048),
                Optional.empty(), Optional.empty(), 1.5, "STATIC")), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aScanHoldsAtMost500FindingsAndTheOverflowRollsBack() {
        UUID scanId = consentedScan();
        List<FindingInput> full = IntStream.range(0, 500).mapToObj(i -> World.tlsFinding("src/A.java", "A#" + i)).toList();
        assertThat(w.recordFindings.execute(new RecordFindingsCommand(scanId, full, Optional.empty(), "UI")).createdCount()).isEqualTo(500);
        int events = w.outbox().size();
        assertProblem(() -> w.record(scanId, World.tlsFinding("src/B.java", "B#extra")), ProblemCode.FINDING_LIMIT_EXCEEDED);
        assertThat(w.db.findings).hasSize(500);
        assertThat(w.db.sourceFiles).hasSize(1);
        assertThat(w.outbox()).hasSize(events);
        // Sending existing findings again does not use up the limit.
        assertThat(w.recordFindings.execute(new RecordFindingsCommand(scanId, full, Optional.empty(), "UI")).existingCount()).isEqualTo(500);
    }

    @Test
    void aFileHasOneKind() {
        UUID scanId = consentedScan();
        assertProblem(() -> w.record(scanId, World.tlsFinding("src/A.java", "A#x"),
                World.finding("src/A.java", "A#y", "RSA", "CERTIFICATE", "CONFIG", "P3", 2048)), ProblemCode.VALIDATION_FAILED);
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        assertProblem(() -> w.record(scanId, World.finding("src/A.java", "A#z", "RSA", "CERTIFICATE", "CONFIG", "P3", 2048)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aRetryWithTheSameIdempotencyKeyDoesNotStoreAnythingTwice() {
        UUID scanId = consentedScan();
        RecordFindingsCommand command = new RecordFindingsCommand(scanId, List.of(World.tlsFinding("src/A.java", "A#x")), World.idem("f1", "d"), "UI");
        RecordFindingsResult first = w.recordFindings.execute(command);
        RecordFindingsResult replay = w.recordFindings.execute(command);
        assertThat(first.createdCount()).isEqualTo(1);
        assertThat(replay.createdCount()).isZero();
        assertThat(replay.existingCount()).isEqualTo(1);
        assertThat(w.db.findings).hasSize(1);
        assertThat(w.outbox()).hasSize(1);
        assertProblem(() -> w.recordFindings.execute(new RecordFindingsCommand(scanId, List.of(World.tlsFinding("src/A.java", "A#y")),
                World.idem("f1", "other"), "UI")), ProblemCode.IDEMPOTENCY_CONFLICT);
    }

    @Test
    void findingsCanBeListedFilteredAndRead() {
        UUID scanId = consentedScan();
        w.record(scanId, World.tlsFinding("src/A.java", "A#one"), World.finding("src/B.java", "B#sign", "SHA1", "SIGNATURE", "CODE", "P0", null));
        PageView<FindingView> p0 = w.listFindings.execute(new ListFindingsQuery(scanId, Optional.of("P0"), Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.empty(), 0, 10));
        assertThat(p0.items()).hasSize(1);
        assertThat(p0.items().get(0).path()).isEqualTo("src/B.java");
        assertThat(w.listFindings.execute(new ListFindingsQuery(scanId, Optional.empty(), Optional.of("RSA"), Optional.of("TLS_KEY_EXCHANGE"),
                Optional.of("CODE"), Optional.of("STATIC"), 0, 10)).total()).isEqualTo(1);
        FindingView one = w.getFinding.execute(new GetFindingQuery(p0.items().get(0).id()));
        assertThat(one.scanId()).isEqualTo(scanId);
        assertThat(one.algorithmFamily()).isEqualTo("SHA1");
        assertProblem(() -> w.getFinding.execute(new GetFindingQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
        assertProblem(() -> w.listFindings.execute(new ListFindingsQuery(scanId, Optional.of("P9"), Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.empty(), 0, 10)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.listFindings.execute(new ListFindingsQuery(new UUID(9, 9), Optional.empty(), Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.empty(), 0, 10)), ProblemCode.NOT_FOUND);
    }
}
