package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.ProjectRuntimeChanged;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileUseCase;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.RuntimeProfileWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Records the project's Java and Spring Boot version when it changed, and tells the warehouse (D-143). */
public final class RecordRuntimeProfileService implements RecordRuntimeProfileUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final ConsentGate consentGate;
    private final RuntimeProfileReader reader;
    private final RuntimeProfileWriter writer;
    private final EventRecorder events;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;

    public RecordRuntimeProfileService(
            TransactionRunner tx, ProjectLock projectLock, ConsentGate consentGate, RuntimeProfileReader reader,
            RuntimeProfileWriter writer, EventRecorder events, IdempotentExecutor idempotency, AuditRecorder audit, Clock clock) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.consentGate = consentGate;
        this.reader = reader;
        this.writer = writer;
        this.events = events;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
    }

    @Override
    public RuntimeProfileView execute(RecordRuntimeProfileCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        Guard.valid(() -> new RuntimeProfile(1, input.javaVersion(), input.springBootVersion(), clock.now()));
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.RUNTIME_PROFILE_RECORDED,
                replay -> reader.current(input.projectId())
                        .map(p -> ViewMapper.runtimeProfile(p, replay.statusCode() == 201))
                        .orElseThrow(() -> Fail.notFound("runtime profile")),
                () -> {
                    Project project = projectLock.noKeyUpdate(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
                    boolean consented = consentGate.warehouseConsented(project.id());
                    Optional<RuntimeProfile> current = reader.current(project.id());
                    if (current.filter(p -> p.sameVersionsAs(input.javaVersion(), input.springBootVersion())).isPresent()) {
                        return new IdempotentExecutor.Outcome<>(ViewMapper.runtimeProfile(current.get(), false), 200, Optional.of(project.id()));
                    }
                    int next = current.map(p -> p.sequenceNo() + 1).orElse(1);
                    RuntimeProfile profile = new RuntimeProfile(next, input.javaVersion(), input.springBootVersion(), clock.now());
                    writer.insert(project.id(), profile);
                    events.recordIfConsented(consented, project.key(),
                            new ProjectRuntimeChanged(current.map(RecordRuntimeProfileService::snapshot), snapshot(profile)));
                    audit.record(AuditAction.RUNTIME_PROFILE_RECORDED, Optional.of(project.key()), Optional.of(project.id()), caller);
                    return new IdempotentExecutor.Outcome<>(ViewMapper.runtimeProfile(profile, true), 201, Optional.of(project.id()));
                }));
    }

    private static ProjectRuntimeChanged.Snapshot snapshot(RuntimeProfile profile) {
        return new ProjectRuntimeChanged.Snapshot(profile.javaVersion(), profile.springBootVersion());
    }
}
