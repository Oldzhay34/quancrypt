package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.GetProjectQuery;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.ListProjectsQuery;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.RequestDigest;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.ProjectDetailView;
import com.quancrypt.core.port.inbound.view.ProjectView;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static com.quancrypt.core.fake.Problems.assertProblem;
class ProjectUseCasesTest {

    private final World w = new World();

    private ProjectView register(String identity, String name) {
        return w.registerProject.execute(new RegisterProjectCommand(identity, name, Optional.empty(), "UI"));
    }

    @Test
    void registeringStoresOnlyTheHmacOfTheIdentityAndAuditsIt() {
        ProjectView view = register("/work/demo", "Demo");
        assertThat(view.created()).isTrue();
        assertThat(view.projectKey()).isEqualTo(ScanArtifact.sha256Hex("/work/demo".getBytes(StandardCharsets.UTF_8)));
        assertThat(w.db.projects).hasSize(1);
        assertThat(w.auditActions()).containsExactly(AuditAction.PROJECT_REGISTERED);
        assertThat(w.db.audit.get(0).projectKey()).hasValue(new ProjectKey(view.projectKey()));
    }

    @Test
    void registeringTheSameIdentityAgainReturnsTheSameProjectWithoutANewAuditRow() {
        ProjectView first = register("/work/demo", "Demo");
        ProjectView second = register("/work/demo", "Other name");
        assertThat(second.created()).isFalse();
        assertThat(second.id()).isEqualTo(first.id());
        assertThat(w.db.projects).hasSize(1);
        assertThat(w.auditActions()).hasSize(1);
    }

    @Test
    void invalidRegistrationsAreValidationFailures() {
        assertProblem(() -> register(" ", "Demo"), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> register("x".repeat(2049), "Demo"), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> register("/work/demo", " "), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.registerProject.execute(new RegisterProjectCommand("/work/demo", "Demo", Optional.empty(), "ROBOT")),
                ProblemCode.VALIDATION_FAILED);
        assertThat(w.db.projects).isEmpty();
    }

    @Test
    void anIdempotentRetryGetsTheSameProjectAndADifferentRequestIsAConflict() {
        RegisterProjectCommand first = new RegisterProjectCommand("/work/demo", "Demo", Optional.of("k1"), "UI");
        ProjectView created = w.registerProject.execute(first);
        ProjectView replay = w.registerProject.execute(first);
        assertThat(replay.id()).isEqualTo(created.id());
        assertThat(replay.created()).isTrue();
        assertThat(w.db.projects).hasSize(1);
        // The digest covers the HMAC project key, never the identity (D-136).
        assertThat(w.db.idempotency.values().iterator().next().requestDigest())
                .isEqualTo(RequestDigest.of("POST", "/api/v1/projects", created.projectKey(), "Demo"));
        assertProblem(() -> w.registerProject.execute(new RegisterProjectCommand("/work/demo", "Renamed", Optional.of("k1"), "UI")),
                ProblemCode.IDEMPOTENCY_CONFLICT);
    }

    @Test
    void aProjectCanBeReadWithItsCurrentRuntimeProfile() {
        UUID id = w.project();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "21.0.1", Optional.of("3.5.0"), Optional.empty(), "UI"));
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "25.0.4.1", Optional.of("4.1.1"), Optional.empty(), "UI"));
        ProjectDetailView detail = w.getProject.execute(new GetProjectQuery(id));
        assertThat(detail.currentRuntimeProfile()).hasValueSatisfying(p -> assertThat(p.javaVersion()).isEqualTo("25.0.4.1"));
        assertProblem(() -> w.getProject.execute(new GetProjectQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
    }

    @Test
    void projectsAreListedNewestFirstInValidatedPages() {
        register("/a", "A");
        register("/b", "B");
        register("/c", "C");
        PageView<ProjectView> page = w.listProjects.execute(new ListProjectsQuery(0, 2));
        assertThat(page.items()).extracting(ProjectView::displayName).containsExactly("C", "B");
        assertThat(page.total()).isEqualTo(3);
        assertThat(w.listProjects.execute(new ListProjectsQuery(1, 2)).items()).extracting(ProjectView::displayName).containsExactly("A");
        assertProblem(() -> w.listProjects.execute(new ListProjectsQuery(0, 0)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.listProjects.execute(new ListProjectsQuery(0, 201)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.listProjects.execute(new ListProjectsQuery(-1, 10)), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void theRuntimeProfileGrowsOnlyWhenTheVersionsChange() {
        UUID id = w.project();
        RuntimeProfileView first = w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "25", Optional.empty(), Optional.empty(), "UI"));
        RuntimeProfileView same = w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "25", Optional.empty(), Optional.empty(), "UI"));
        RuntimeProfileView changed = w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "26", Optional.empty(), Optional.empty(), "UI"));
        assertThat(first.sequenceNo()).isEqualTo(1);
        assertThat(first.created()).isTrue();
        assertThat(same.created()).isFalse();
        assertThat(same.sequenceNo()).isEqualTo(1);
        assertThat(changed.sequenceNo()).isEqualTo(2);
        assertThat(w.db.profiles.get(id)).hasSize(2);
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.RUNTIME_PROFILE_RECORDED)).hasSize(2);
        assertThat(w.db.lockLog).contains("project:noKeyUpdate");
    }

    @Test
    void aRuntimeChangeReachesTheOutboxOnlyWithWarehouseConsent() {
        UUID noConsent = w.project();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(noConsent, "25", Optional.empty(), Optional.empty(), "UI"));
        assertThat(w.outbox()).isEmpty();
        UUID consented = w.registerProject.execute(new RegisterProjectCommand("/other", "Other", Optional.empty(), "UI")).id();
        w.grantConsent.execute(new GrantConsentCommand(consented, "WAREHOUSE_ANALYTICS", 1, Optional.empty(), Optional.empty(), "UI"));
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(consented, "21", Optional.empty(), Optional.empty(), "UI"));
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(consented, "25", Optional.of("4.1.1"), Optional.empty(), "UI"));
        assertThat(w.outbox()).hasSize(2);
        assertThat(w.outbox().get(0).payload().get("previous")).isNull();
        assertThat(w.outbox().get(1).payload().get("previous")).isNotNull();
        assertThat(w.outbox()).allSatisfy(r -> assertThat(r.type()).isEqualTo(EventType.PROJECT_RUNTIME_CHANGED));
    }

    @Test
    void invalidRuntimeProfilesAndUnknownProjectsAreRejected() {
        UUID id = w.project();
        assertProblem(() -> w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "not a version", Optional.empty(), Optional.empty(), "UI")),
                ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(new UUID(9, 9), "25", Optional.empty(), Optional.empty(), "UI")),
                ProblemCode.NOT_FOUND);
    }

    @Test
    void deletingAProjectRemovesTheTreeRevokesTheEventsAndKeepsTheAuditTrail() {
        UUID id = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(id);
        w.record(scanId, World.tlsFinding("src/A.java", "A#connect"));
        w.complete(scanId);
        w.relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(id, "25", Optional.empty(), Optional.empty(), "UI"));
        long sent = w.db.published.size();
        ProjectView project = w.getProject.execute(new GetProjectQuery(id)).project();

        w.db.lockLog.clear();
        w.deleteProject.execute(new DeleteProjectCommand(id, "UI"));

        assertThat(w.db.lockLog).containsExactly("project:update", "consent:updateAll");
        assertThat(w.db.projects).isEmpty();
        assertThat(w.db.scans).isEmpty();
        assertThat(w.db.findings).isEmpty();
        assertThat(w.db.sourceFiles).isEmpty();
        assertThat(w.db.consents).isEmpty();
        assertThat(w.db.outbox.stream().filter(r -> w.db.published.contains(r.id()))).hasSize((int) sent);
        List<OutboxRecord> pending = w.db.outbox.stream().filter(r -> !w.db.published.contains(r.id())).toList();
        assertThat(pending).hasSize(2).allSatisfy(r -> {
            assertThat(r.type()).isEqualTo(EventType.CONSENT_REVOKED);
            assertThat(r.payload()).containsEntry("delete_requested", true);
            assertThat(r.projectKey().value()).isEqualTo(project.projectKey());
        });
        assertThat(w.auditActions()).contains(AuditAction.PROJECT_DELETED);
        assertProblem(() -> w.deleteProject.execute(new DeleteProjectCommand(id, "UI")), ProblemCode.NOT_FOUND);
    }
}
