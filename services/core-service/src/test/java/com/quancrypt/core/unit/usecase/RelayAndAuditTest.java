package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.GetAuditLogQuery;
import com.quancrypt.core.port.inbound.GetProjectQuery;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.view.AuditEntryView;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.RelayResult;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static com.quancrypt.core.fake.Problems.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

class RelayAndAuditTest {

    private final World w = new World();

    private void pendingEvents() {
        UUID scanId = w.runningScan(w.projectWithWarehouseConsent());
        w.record(scanId, World.tlsFinding("src/A.java", "A#one"), World.tlsFinding("src/A.java", "A#two"));
    }

    @Test
    void pendingEventsAreSentMarkedAndAuditedOnceWithoutAProjectKey() {
        pendingEvents();
        RelayResult result = w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));
        assertThat(result.relayedCount()).isEqualTo(2);
        assertThat(result.remainingCount()).isZero();
        assertThat(w.publisher.seen()).hasSize(2);
        assertThat(w.db.published).hasSize(2);
        AuditEntry audit = w.db.audit.get(w.db.audit.size() - 1);
        assertThat(audit.action()).isEqualTo(AuditAction.OUTBOX_EVENTS_RELAYED);
        assertThat(audit.projectKey()).isEmpty();
        assertThat(audit.caller()).isEqualTo(CallerKind.INTERNAL);
        int audits = w.db.audit.size();
        assertThat(w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100)).relayedCount()).isZero();
        assertThat(w.db.audit).hasSize(audits);
    }

    @Test
    void theBatchSizeLimitsOneRunAndTheRestStaysPending() {
        pendingEvents();
        RelayResult result = w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(1));
        assertThat(result.relayedCount()).isEqualTo(1);
        assertThat(result.remainingCount()).isEqualTo(1);
    }

    @Test
    void aReceiverThatRefusesOrFailsLeavesTheEventsPendingForTheNextRun() {
        pendingEvents();
        w.publisher.acceptAll(false);
        assertThat(w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100)).relayedCount()).isZero();
        w.publisher.failing(true);
        RelayResult failed = w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));
        assertThat(failed.relayedCount()).isZero();
        assertThat(failed.publishFailed()).isTrue();
        assertThat(failed.remainingCount()).isEqualTo(2);
        assertThat(w.db.published).isEmpty();
        assertThat(w.auditActions()).doesNotContain(AuditAction.OUTBOX_EVENTS_RELAYED);
        w.publisher.failing(false);
        w.publisher.acceptAll(true);
        assertThat(w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100)).relayedCount()).isEqualTo(2);
    }

    @Test
    void anIdAnswerThatWasNeverSentDoesNotMarkAnything() {
        pendingEvents();
        w.publisher.answerWithForeignId(true);
        RelayResult result = w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));
        assertThat(result.relayedCount()).isZero();
        assertThat(w.db.published).isEmpty();
        assertThat(result.remainingCount()).isEqualTo(2);
    }

    @Test
    void theBatchSizeIsValidated() {
        assertProblem(() -> w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(0)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(201)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void idempotencyRecordsOlderThan24HoursArePurgedByTheRelay() {
        UUID projectId = w.project();
        w.startScan.execute(new StartScanCommand(projectId, World.idem("old", "d"), "UI"));
        w.clock.advance(Duration.ofHours(23));
        w.startScan.execute(new StartScanCommand(projectId, World.idem("old", "d"), "UI"));
        w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(10));
        assertThat(w.db.idempotency).hasSize(1);
        w.clock.advance(Duration.ofHours(2));
        w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(10));
        assertThat(w.db.idempotency).isEmpty();
    }

    @Test
    void theAuditLogOfAProjectKeyIsPagedNewestFirst() {
        UUID projectId = w.project();
        String key = w.getProject.execute(new GetProjectQuery(projectId)).project().projectKey();
        w.runningScan(projectId);
        PageView<AuditEntryView> page = w.getAuditLog.execute(new GetAuditLogQuery(key, 0, 10));
        assertThat(page.items()).extracting(AuditEntryView::action).containsExactly("SCAN_STARTED", "PROJECT_REGISTERED");
        assertThat(page.items()).allSatisfy(e -> assertThat(e.projectKey()).hasValue(key));
        assertThat(w.getAuditLog.execute(new GetAuditLogQuery(key, 1, 1)).items()).extracting(AuditEntryView::action).containsExactly("PROJECT_REGISTERED");
        assertThat(w.getAuditLog.execute(new GetAuditLogQuery("b".repeat(64), 0, 10)).total()).isZero();
        assertProblem(() -> w.getAuditLog.execute(new GetAuditLogQuery("short", 0, 10)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.getAuditLog.execute(new GetAuditLogQuery(key, 0, 0)), ProblemCode.VALIDATION_FAILED);
    }
}
