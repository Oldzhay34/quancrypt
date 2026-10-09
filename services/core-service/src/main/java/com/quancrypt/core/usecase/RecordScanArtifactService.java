package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordScanArtifactCommand;
import com.quancrypt.core.port.inbound.RecordScanArtifactUseCase;
import com.quancrypt.core.port.inbound.view.ScanArtifactView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ScanArtifactWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;
import java.util.Set;

/** Stores the CBOM file of a running scan with the SHA-256 computed here (D-139q). */
public final class RecordScanArtifactService implements RecordScanArtifactUseCase {

    private static final Set<String> ACCEPTED_TYPES = Set.of("application/vnd.cyclonedx+json", "application/json");

    private final TransactionRunner tx;
    private final ScanAccess access;
    private final ScanArtifactWriter writer;
    private final AuditRecorder audit;
    private final Clock clock;

    public RecordScanArtifactService(TransactionRunner tx, ScanAccess access, ScanArtifactWriter writer, AuditRecorder audit, Clock clock) {
        this.tx = tx;
        this.access = access;
        this.writer = writer;
        this.audit = audit;
        this.clock = clock;
    }

    @Override
    public ScanArtifactView execute(RecordScanArtifactCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        if (input.content().length > ScanArtifact.MAX_BYTES) {
            throw Fail.problem(ProblemCode.PAYLOAD_TOO_LARGE, "the artifact is larger than 20 MiB");
        }
        if (input.contentType() == null || !ACCEPTED_TYPES.contains(input.contentType())) {
            throw Fail.problem(ProblemCode.UNSUPPORTED_MEDIA_TYPE, "the artifact must be CycloneDX JSON");
        }
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            LockedScan locked = access.runningForUpdate(input.scanId());
            ScanArtifact artifact = ScanArtifact.of(locked.scan().id(), input.contentType(), input.content(), clock.now());
            writer.save(artifact);
            audit.record(AuditAction.SCAN_ARTIFACT_RECORDED, Optional.of(locked.project().key()), Optional.of(locked.scan().id()), caller);
            return new ScanArtifactView(artifact.scanId(), artifact.contentType(), artifact.sha256(), artifact.createdAt());
        });
    }
}
