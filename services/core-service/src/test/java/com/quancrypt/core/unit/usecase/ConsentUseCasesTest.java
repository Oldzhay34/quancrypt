package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.GetConsentsQuery;
import com.quancrypt.core.port.inbound.GetPrivacyNoticeQuery;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RevokeConsentCommand;
import com.quancrypt.core.port.inbound.view.ConsentView;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static com.quancrypt.core.fake.Problems.assertProblem;
class ConsentUseCasesTest {

    private final World w = new World();

    private ConsentView grant(UUID projectId, String type, Integer expectedVersion) {
        return w.grantConsent.execute(new GrantConsentCommand(projectId, type, 1, Optional.ofNullable(expectedVersion), Optional.empty(), "UI"));
    }

    private ConsentView revoke(UUID projectId, String type, int version) {
        return w.revokeConsent.execute(new RevokeConsentCommand(projectId, type, version, "UI"));
    }

    @Test
    void theLatestPrivacyNoticeCanBeRead() {
        assertThat(w.getPrivacyNotice.execute(new GetPrivacyNoticeQuery()).version()).isEqualTo(1);
        w.db.notices.clear();
        assertProblem(() -> w.getPrivacyNotice.execute(new GetPrivacyNoticeQuery()), ProblemCode.NOT_FOUND);
    }

    @Test
    void aFirstGrantCreatesTheConsentAtVersionZeroAndAuditsIt() {
        UUID id = w.project();
        ConsentView view = grant(id, "WAREHOUSE_ANALYTICS", null);
        assertThat(view.created()).isTrue();
        assertThat(view.version()).isZero();
        assertThat(view.revokedAt()).isEmpty();
        assertThat(w.auditActions()).containsExactly(AuditAction.PROJECT_REGISTERED, AuditAction.CONSENT_GRANTED);
        assertThat(w.db.lockLog).containsExactly("project:keyShare");
    }

    @Test
    void grantingAnActiveConsentAgainChangesNothing() {
        UUID id = w.project();
        grant(id, "MODEL_TRAINING", null);
        int audits = w.db.audit.size();
        ConsentView again = grant(id, "MODEL_TRAINING", null);
        assertThat(again.created()).isFalse();
        assertThat(w.db.audit).hasSize(audits);
        assertThat(w.db.consents).hasSize(1);
    }

    @Test
    void onlyTheLatestNoticeVersionAndKnownTypesAreAccepted() {
        UUID id = w.project();
        assertProblem(() -> w.grantConsent.execute(new GrantConsentCommand(id, "WAREHOUSE_ANALYTICS", 2, Optional.empty(), Optional.empty(), "UI")),
                ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> grant(id, "MARKETING", null), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> grant(new UUID(9, 9), "WAREHOUSE_ANALYTICS", null), ProblemCode.NOT_FOUND);
    }

    @Test
    void aRevokedConsentIsGrantedAgainOnlyWithTheVersionTheClientSaw() {
        UUID id = w.project();
        ConsentView granted = grant(id, "WAREHOUSE_ANALYTICS", null);
        ConsentView revoked = revoke(id, "WAREHOUSE_ANALYTICS", granted.version());
        assertThat(revoked.revokedAt()).isPresent();
        assertThat(revoked.version()).isEqualTo(1);
        assertProblem(() -> grant(id, "WAREHOUSE_ANALYTICS", null), ProblemCode.PRECONDITION_REQUIRED);
        assertProblem(() -> grant(id, "WAREHOUSE_ANALYTICS", 0), ProblemCode.CONCURRENT_MODIFICATION);
        ConsentView again = grant(id, "WAREHOUSE_ANALYTICS", 1);
        assertThat(again.revokedAt()).isEmpty();
        assertThat(again.version()).isEqualTo(2);
        assertThat(again.created()).isFalse();
    }

    @Test
    void revokingNeedsTheCurrentVersionAndIsIdempotentWhenAlreadyRevoked() {
        UUID id = w.project();
        grant(id, "WAREHOUSE_ANALYTICS", null);
        assertProblem(() -> revoke(id, "WAREHOUSE_ANALYTICS", 5), ProblemCode.CONCURRENT_MODIFICATION);
        revoke(id, "WAREHOUSE_ANALYTICS", 0);
        int events = w.outbox().size();
        int audits = w.db.audit.size();
        ConsentView again = revoke(id, "WAREHOUSE_ANALYTICS", 0);
        assertThat(again.revokedAt()).isPresent();
        assertThat(w.outbox()).hasSize(events);
        assertThat(w.db.audit).hasSize(audits);
        assertProblem(() -> revoke(id, "MODEL_TRAINING", 0), ProblemCode.NOT_FOUND);
        assertProblem(() -> revoke(new UUID(9, 9), "WAREHOUSE_ANALYTICS", 0), ProblemCode.NOT_FOUND);
    }

    @Test
    void revokingWarehouseAnalyticsClearsUnsentEventsButKeepsEarlierRevocations() {
        UUID id = w.projectWithWarehouseConsent();
        grant(id, "MODEL_TRAINING", null);
        revoke(id, "MODEL_TRAINING", 0);
        UUID scanId = w.runningScan(id);
        w.record(scanId, World.tlsFinding("src/A.java", "A#connect"));
        assertThat(w.outboxTypes()).containsExactly(EventType.CONSENT_REVOKED, EventType.FINDING_DETECTED);

        revoke(id, "WAREHOUSE_ANALYTICS", 0);

        assertThat(w.outboxTypes()).containsExactly(EventType.CONSENT_REVOKED, EventType.CONSENT_REVOKED);
        assertThat(w.outbox().get(1).payload()).containsEntry("consent_type", "WAREHOUSE_ANALYTICS").containsEntry("delete_requested", false);
    }

    @Test
    void revokingModelTrainingWritesARevocationEventAndKeepsPendingEvents() {
        UUID id = w.projectWithWarehouseConsent();
        grant(id, "MODEL_TRAINING", null);
        UUID scanId = w.runningScan(id);
        w.record(scanId, World.tlsFinding("src/A.java", "A#connect"));
        revoke(id, "MODEL_TRAINING", 0);
        assertThat(w.outboxTypes()).containsExactly(EventType.FINDING_DETECTED, EventType.CONSENT_REVOKED);
    }

    @Test
    void aRevocationEventIsWrittenEvenWhenThereWasNeverWarehouseConsent() {
        UUID id = w.project();
        grant(id, "MODEL_TRAINING", null);
        revoke(id, "MODEL_TRAINING", 0);
        assertThat(w.outboxTypes()).containsExactly(EventType.CONSENT_REVOKED);
    }

    @Test
    void consentsAreListedPerProject() {
        UUID id = w.project();
        grant(id, "WAREHOUSE_ANALYTICS", null);
        grant(id, "MODEL_TRAINING", null);
        assertThat(w.getConsents.execute(new GetConsentsQuery(id)).items()).extracting(ConsentView::consentType)
                .containsExactly("WAREHOUSE_ANALYTICS", "MODEL_TRAINING");
        assertProblem(() -> w.getConsents.execute(new GetConsentsQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
    }

    @Test
    void aGrantRetryWithTheSameIdempotencyKeyGetsTheSameConsent() {
        UUID id = w.project();
        GrantConsentCommand command = new GrantConsentCommand(id, "WAREHOUSE_ANALYTICS", 1, Optional.empty(), World.idem("g1", "d"), "UI");
        ConsentView first = w.grantConsent.execute(command);
        ConsentView replay = w.grantConsent.execute(command);
        assertThat(replay.version()).isEqualTo(first.version());
        assertThat(w.db.consents).hasSize(1);
        assertProblem(() -> w.grantConsent.execute(new GrantConsentCommand(id, "WAREHOUSE_ANALYTICS", 1, Optional.empty(), World.idem("g1", "other"), "UI")),
                ProblemCode.IDEMPOTENCY_CONFLICT);
    }
}
