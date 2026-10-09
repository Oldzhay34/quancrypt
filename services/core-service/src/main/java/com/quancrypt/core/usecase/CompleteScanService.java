package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.ScanCompleted;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CompleteScanUseCase;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingStats;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.ScanWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** Finishes a running scan as COMPLETED or FAILED; a retry with the same outcome gets the same scan back. */
public final class CompleteScanService implements CompleteScanUseCase {

    private final TransactionRunner tx;
    private final ScanAccess access;
    private final ScanReader scans;
    private final ScanWriter scanWriter;
    private final FindingReader findings;
    private final RuntimeProfileReader profiles;
    private final EventRecorder events;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;

    public CompleteScanService(
            TransactionRunner tx, ScanAccess access, ScanReader scans, ScanWriter scanWriter, FindingReader findings,
            RuntimeProfileReader profiles, EventRecorder events, IdempotentExecutor idempotency, AuditRecorder audit, Clock clock) {
        this.tx = tx;
        this.access = access;
        this.scans = scans;
        this.scanWriter = scanWriter;
        this.findings = findings;
        this.profiles = profiles;
        this.events = events;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
    }

    @Override
    public ScanView execute(CompleteScanCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        ScanStatus outcome = Codes.parse(ScanStatus.class, input.outcome(), "outcome");
        if (outcome == ScanStatus.RUNNING) {
            throw Fail.validation("outcome must be COMPLETED or FAILED");
        }
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.SCAN_COMPLETED,
                replay -> scans.find(replay.resourceId().orElseThrow()).map(ViewMapper::scan).orElseThrow(() -> Fail.notFound("scan")),
                () -> {
                    LockedScan locked = access.forCompletion(input.scanId());
                    Scan scan = locked.scan();
                    UUID projectId = locked.project().id();
                    Instant now = clock.now();
                    if (!scan.isRunning() || !scanWriter.finishIfRunning(scan.id(), outcome, now)) {
                        Scan current = scans.find(scan.id()).orElseThrow(() -> Fail.notFound("scan"));
                        if (current.status() == outcome) {
                            return new IdempotentExecutor.Outcome<>(ViewMapper.scan(current), 200, Optional.of(current.id()));
                        }
                        throw Fail.problem(ProblemCode.SCAN_NOT_RUNNING, "the scan is not running");
                    }
                    Scan finished = scan.finish(outcome, now);
                    if (outcome == ScanStatus.COMPLETED) {
                        FindingStats stats = findings.stats(scan.id());
                        Optional<RuntimeProfile> profile = scan.runtimeProfileSequenceNo().flatMap(seq -> profiles.bySequence(projectId, seq));
                        events.recordIfConsented(locked.warehouseConsent(), locked.project().key(), new ScanCompleted(
                                stats.total(), stats.byPriority(), profile.map(RuntimeProfile::javaVersion),
                                profile.flatMap(RuntimeProfile::springBootVersion), Duration.between(scan.startedAt(), now).toSeconds()));
                    }
                    audit.record(AuditAction.SCAN_COMPLETED, Optional.of(locked.project().key()), Optional.of(scan.id()), caller);
                    return new IdempotentExecutor.Outcome<>(ViewMapper.scan(finished), 200, Optional.of(scan.id()));
                }));
    }
}
