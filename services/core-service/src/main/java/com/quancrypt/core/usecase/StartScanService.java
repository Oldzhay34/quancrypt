package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.exception.ScanAlreadyRunningException;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.StartScanUseCase;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.ScanWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Starts a scan of a project; the partial unique index allows one running scan per project. */
public final class StartScanService implements StartScanUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final RuntimeProfileReader profiles;
    private final ScanReader scanReader;
    private final ScanWriter scanWriter;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;
    private final IdGenerator ids;

    public StartScanService(
            TransactionRunner tx, ProjectLock projectLock, RuntimeProfileReader profiles, ScanReader scanReader,
            ScanWriter scanWriter, IdempotentExecutor idempotency, AuditRecorder audit, Clock clock, IdGenerator ids) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.profiles = profiles;
        this.scanReader = scanReader;
        this.scanWriter = scanWriter;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
        this.ids = ids;
    }

    @Override
    public ScanView execute(StartScanCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.SCAN_STARTED,
                replay -> scanReader.find(replay.resourceId().orElseThrow()).map(ViewMapper::scan).orElseThrow(() -> Fail.notFound("scan")),
                () -> {
                    Project project = projectLock.keyShare(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
                    Optional<Integer> profile = profiles.current(project.id()).map(RuntimeProfile::sequenceNo);
                    Scan scan = Scan.start(ids.next(), project.id(), profile, clock.now());
                    try {
                        scanWriter.insertRunning(scan);
                    } catch (ScanAlreadyRunningException e) {
                        throw Fail.problem(ProblemCode.SCAN_ALREADY_RUNNING, "the project already has a running scan");
                    }
                    audit.record(AuditAction.SCAN_STARTED, Optional.of(project.key()), Optional.of(scan.id()), caller);
                    return new IdempotentExecutor.Outcome<>(ViewMapper.scan(scan), 201, Optional.of(scan.id()));
                }));
    }
}
