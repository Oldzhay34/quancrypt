package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.DuplicateConsentException;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.GrantConsentUseCase;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.view.ConsentView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.ConsentWriter;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.PrivacyNoticeReader;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Grants a consent, or grants it again after a revoke with the version the client saw (D-21, D-135). */
public final class GrantConsentService implements GrantConsentUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final ConsentReader consentReader;
    private final ConsentWriter consentWriter;
    private final PrivacyNoticeReader notices;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;
    private final IdGenerator ids;

    public GrantConsentService(
            TransactionRunner tx, ProjectLock projectLock, ConsentReader consentReader,
            ConsentWriter consentWriter, PrivacyNoticeReader notices, IdempotentExecutor idempotency, AuditRecorder audit,
            Clock clock, IdGenerator ids) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.consentReader = consentReader;
        this.consentWriter = consentWriter;
        this.notices = notices;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
        this.ids = ids;
    }

    @Override
    public ConsentView execute(GrantConsentCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        ConsentType type = Codes.parse(ConsentType.class, input.consentType(), "consentType");
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.CONSENT_GRANTED,
                replay -> consentReader.find(input.projectId(), type)
                        .map(c -> ViewMapper.consent(c, replay.statusCode() == 201))
                        .orElseThrow(() -> Fail.notFound("consent")),
                () -> {
                    Project project = projectLock.keyShare(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
                    PrivacyNotice notice = notices.latest().orElseThrow(() -> Fail.notFound("privacy notice"));
                    if (input.privacyNoticeVersion() != notice.version()) {
                        throw Fail.validation("only the latest privacy notice version " + notice.version() + " can be accepted");
                    }
                    Optional<Consent> existing = consentReader.find(project.id(), type);
                    if (existing.isEmpty()) {
                        Consent first = Consent.firstGrant(ids.next(), project.id(), type, notice, clock.now());
                        try {
                            consentWriter.insert(first);
                        } catch (DuplicateConsentException e) {
                            throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, "the consent was granted concurrently");
                        }
                        audit.record(AuditAction.CONSENT_GRANTED, Optional.of(project.key()), Optional.of(first.id()), caller);
                        return new IdempotentExecutor.Outcome<>(ViewMapper.consent(first, true), 201, Optional.of(first.id()));
                    }
                    Consent current = existing.get();
                    if (current.isActive()) {
                        return new IdempotentExecutor.Outcome<>(ViewMapper.consent(current, false), 200, Optional.of(current.id()));
                    }
                    int expected = input.expectedVersion()
                            .orElseThrow(() -> Fail.problem(ProblemCode.PRECONDITION_REQUIRED, "If-Match is required to grant a revoked consent again"));
                    if (expected != current.version()) {
                        throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, "the consent was changed by someone else");
                    }
                    Consent regranted = current.regrant(notice, clock.now());
                    try {
                        consentWriter.update(regranted, expected);
                    } catch (ConcurrentModificationException e) {
                        throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, e.getMessage());
                    }
                    audit.record(AuditAction.CONSENT_GRANTED, Optional.of(project.key()), Optional.of(regranted.id()), caller);
                    return new IdempotentExecutor.Outcome<>(ViewMapper.consent(regranted, false), 200, Optional.of(regranted.id()));
                }));
    }
}
