package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.ConsentRevoked;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.DeleteProjectUseCase;
import com.quancrypt.core.port.outbound.ConsentLock;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.OutboxWriter;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.ProjectWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Deletes a project: pending events go, revocation events are written first, then the tree is cascaded (D-127). */
public final class DeleteProjectService implements DeleteProjectUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final ConsentLock consentLock;
    private final ProjectWriter projectWriter;
    private final OutboxWriter outbox;
    private final EventRecorder events;
    private final AuditRecorder audit;

    public DeleteProjectService(
            TransactionRunner tx, ProjectLock projectLock, ConsentLock consentLock, ProjectWriter projectWriter,
            OutboxWriter outbox, EventRecorder events, AuditRecorder audit) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.consentLock = consentLock;
        this.projectWriter = projectWriter;
        this.outbox = outbox;
        this.events = events;
        this.audit = audit;
    }

    @Override
    public void execute(DeleteProjectCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Project project = projectLock.update(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            consentLock.updateAll(project.id());
            outbox.deletePendingExceptRevocations(project.key());
            for (ConsentType type : ConsentType.values()) {
                events.record(project.key(), new ConsentRevoked(type, true));
            }
            audit.record(AuditAction.PROJECT_DELETED, Optional.of(project.key()), Optional.empty(), caller);
            projectWriter.delete(project.id());
        });
    }
}
