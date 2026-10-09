package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.ConsentRevoked;
import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RevokeConsentCommand;
import com.quancrypt.core.port.inbound.RevokeConsentUseCase;
import com.quancrypt.core.port.inbound.view.ConsentView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.ConsentWriter;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.OutboxWriter;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Revokes a consent; a warehouse revoke clears the unsent events, then a revocation event is always written (D-132). */
public final class RevokeConsentService implements RevokeConsentUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final ConsentReader consentReader;
    private final ConsentWriter consentWriter;
    private final OutboxWriter outbox;
    private final EventRecorder events;
    private final AuditRecorder audit;
    private final Clock clock;

    public RevokeConsentService(
            TransactionRunner tx, ProjectLock projectLock, ConsentReader consentReader, ConsentWriter consentWriter,
            OutboxWriter outbox, EventRecorder events, AuditRecorder audit, Clock clock) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.consentReader = consentReader;
        this.consentWriter = consentWriter;
        this.outbox = outbox;
        this.events = events;
        this.audit = audit;
        this.clock = clock;
    }

    @Override
    public ConsentView execute(RevokeConsentCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        ConsentType type = Codes.parse(ConsentType.class, input.consentType(), "consentType");
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Project project = projectLock.keyShare(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            Consent current = consentReader.find(project.id(), type).orElseThrow(() -> Fail.notFound("consent"));
            if (!current.isActive()) {
                return ViewMapper.consent(current, false);
            }
            if (input.expectedVersion() != current.version()) {
                throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, "the consent was changed by someone else");
            }
            Consent revoked = current.revoke(clock.now());
            try {
                consentWriter.update(revoked, input.expectedVersion());
            } catch (ConcurrentModificationException e) {
                throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, e.getMessage());
            }
            if (type == ConsentType.WAREHOUSE_ANALYTICS) {
                outbox.deletePendingExceptRevocations(project.key());
            }
            events.record(project.key(), new ConsentRevoked(type, false));
            audit.record(AuditAction.CONSENT_REVOKED, Optional.of(project.key()), Optional.of(revoked.id()), caller);
            return ViewMapper.consent(revoked, false);
        });
    }
}
