package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.inbound.Idempotency;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.RegisterProjectUseCase;
import com.quancrypt.core.port.inbound.RequestDigest;
import com.quancrypt.core.port.inbound.view.ProjectView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectKeyHasher;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.ProjectWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Registers a project by the HMAC of its identity; the same identity gives the same project (D-129). */
public final class RegisterProjectService implements RegisterProjectUseCase {

    private static final int MAX_IDENTITY = 2048;

    private final TransactionRunner tx;
    private final ProjectKeyHasher hasher;
    private final ProjectReader reader;
    private final ProjectWriter writer;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;
    private final IdGenerator ids;

    public RegisterProjectService(
            TransactionRunner tx, ProjectKeyHasher hasher, ProjectReader reader, ProjectWriter writer,
            IdempotentExecutor idempotency, AuditRecorder audit, Clock clock, IdGenerator ids) {
        this.tx = tx;
        this.hasher = hasher;
        this.reader = reader;
        this.writer = writer;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
        this.ids = ids;
    }

    @Override
    public ProjectView execute(RegisterProjectCommand input) {
        if (input.identity() == null || input.identity().isBlank() || input.identity().length() > MAX_IDENTITY) {
            throw Fail.validation("identity must be 1.." + MAX_IDENTITY + " characters");
        }
        CallerKind caller = Codes.caller(input.caller());
        ProjectKey key = hasher.hash(input.identity());
        // The digest covers the project key, never the identity itself (D-136).
        Optional<Idempotency> request = input.idempotencyKey()
                .map(k -> new Idempotency(k, RequestDigest.of("POST", "/api/v1/projects", key.value(), String.valueOf(input.displayName()))));
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                request,
                AuditAction.PROJECT_REGISTERED,
                replay -> reader.findById(replay.resourceId().orElseThrow())
                        .map(p -> ViewMapper.project(p, replay.statusCode() == 201))
                        .orElseThrow(() -> Fail.notFound("project")),
                () -> {
                    Project candidate = Guard.valid(() -> new Project(ids.next(), key, input.displayName(), clock.now()));
                    if (writer.insertIfAbsent(candidate)) {
                        audit.record(AuditAction.PROJECT_REGISTERED, Optional.of(key), Optional.of(candidate.id()), caller);
                        return new IdempotentExecutor.Outcome<>(ViewMapper.project(candidate, true), 201, Optional.of(candidate.id()));
                    }
                    Project existing = reader.findByKey(key).orElseThrow(() -> Fail.notFound("project"));
                    return new IdempotentExecutor.Outcome<>(ViewMapper.project(existing, false), 200, Optional.of(existing.id()));
                }));
    }
}
