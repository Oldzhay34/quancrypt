package com.quancrypt.core.unit.facade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.facade.AuditFacade;
import com.quancrypt.core.facade.PlanFacade;
import com.quancrypt.core.facade.ProjectFacade;
import com.quancrypt.core.facade.ScanFacade;
import com.quancrypt.core.facade.dto.ConsentDto;
import com.quancrypt.core.facade.dto.ConsentGrantInput;
import com.quancrypt.core.facade.dto.FindingBatchInput;
import com.quancrypt.core.facade.dto.FindingBatchResultDto;
import com.quancrypt.core.facade.dto.FindingInputDto;
import com.quancrypt.core.facade.dto.PlanInput;
import com.quancrypt.core.facade.dto.PlanItemDto;
import com.quancrypt.core.facade.dto.PlanItemInputDto;
import com.quancrypt.core.facade.dto.PlanItemTransitionInput;
import com.quancrypt.core.facade.dto.ProjectDto;
import com.quancrypt.core.facade.dto.ProjectRegistrationInput;
import com.quancrypt.core.facade.dto.RiskFactorDto;
import com.quancrypt.core.facade.dto.RuntimeProfileInput;
import com.quancrypt.core.facade.dto.ScanCompletionInput;
import com.quancrypt.core.facade.dto.ScanDto;
import com.quancrypt.core.facade.error.ApiProblemException;
import com.quancrypt.core.facade.error.ProblemKind;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.ProblemCode;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** The facades on the in-memory use case fixture: command mapping, idempotency digests, created flags and error translation. */
class FacadeTest {

    private final World world = new World();
    private final ProjectFacade projects = new ProjectFacade(world.registerProject, world.listProjects, world.getProject, world.deleteProject,
            world.recordRuntimeProfile, world.getPrivacyNotice, world.grantConsent, world.revokeConsent, world.getConsents,
            world.saveClarificationAnswers, world.getProjectProfile);
    private final ScanFacade scans = new ScanFacade(world.startScan, world.listScans, world.recordFindings, world.listFindings, world.getFinding,
            world.recordTopology, world.getTopology, world.recordScanArtifact, world.getScanArtifact, world.completeScan, world.getScanSummary);
    private final PlanFacade plans = new PlanFacade(world.createPlan, world.getPlan, world.transitionPlanItem, world.getPlanReport);
    private final AuditFacade audit = new AuditFacade(world.getAuditLog);

    private static ProjectRegistrationInput registration(String identity) {
        return new ProjectRegistrationInput(identity, "Demo");
    }

    private static FindingInputDto finding(String symbol) {
        return new FindingInputDto("src/main/java/Tls.java", symbol, "RSA", "TLS_KEY_EXCHANGE", "CODE", "P1", 2048, 10, 12, 0.9, "STATIC");
    }

    private ProjectDto project() {
        return projects.register(registration("/work/demo"), Optional.empty(), "UI").body();
    }

    // ------------------------------------------------------------------ errors

    @Test
    void everyProblemCodeHasAProblemKindWithTheSameCode() {
        for (ProblemCode code : ProblemCode.values()) {
            ProblemKind kind = ProblemKind.valueOf(code.name());
            assertThat(kind.code()).isEqualTo(code.code());
            assertThat(kind.type()).isEqualTo("https://quancrypt.local/problems/" + code.code());
        }
    }

    @Test
    void useCaseFailuresBecomeApiProblems() {
        UUID unknown = UUID.randomUUID();

        assertThatThrownBy(() -> projects.get(unknown)).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind()).isEqualTo(ProblemKind.NOT_FOUND));
        assertThatThrownBy(() -> projects.list(0, 0)).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind()).isEqualTo(ProblemKind.VALIDATION_FAILED));
        assertThatThrownBy(() -> audit.entries("0".repeat(64), 0, 201)).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind().status()).isEqualTo(400));
    }

    @Test
    void aDetailIsCappedAndNeverNull() {
        assertThat(new ApiProblemException(ProblemKind.NOT_FOUND, "x".repeat(1000)).getMessage()).hasSize(300);
        assertThat(new ApiProblemException(ProblemKind.NOT_FOUND, null).getMessage()).isEqualTo("Not found");
    }

    // ------------------------------------------------------------------ projects and consents

    @Test
    void registeringTwiceIsCreatedThenExisting() {
        var first = projects.register(registration("/work/demo"), Optional.empty(), "UI");
        var again = projects.register(registration("/work/demo"), Optional.empty(), "UI");

        assertThat(first.created()).isTrue();
        assertThat(again.created()).isFalse();
        assertThat(again.body().id()).isEqualTo(first.body().id());
        assertThat(first.body().projectKey()).matches("[0-9a-f]{64}");
        assertThat(projects.list(0, 10).totalElements()).isEqualTo(1);
    }

    @Test
    void theIdempotencyKeyReplaysTheSameRequestAndRefusesAnotherOne() {
        UUID projectId = project().id();
        RuntimeProfileInput body = new RuntimeProfileInput("21", "3.5.0");

        var first = projects.recordRuntimeProfile(projectId, body, Optional.of("k1"), "UI");
        var replay = projects.recordRuntimeProfile(projectId, body, Optional.of("k1"), "UI");

        assertThat(first.created()).isTrue();
        assertThat(replay.body()).isEqualTo(first.body());
        assertThat(world.db.profiles.get(projectId)).hasSize(1);
        assertThatThrownBy(() -> projects.recordRuntimeProfile(projectId, new RuntimeProfileInput("25", null), Optional.of("k1"), "UI"))
                .isInstanceOfSatisfying(ApiProblemException.class, e -> assertThat(e.kind()).isEqualTo(ProblemKind.IDEMPOTENCY_CONFLICT));
        UUID other = projects.register(registration("/work/other"), Optional.empty(), "UI").body().id();
        assertThatThrownBy(() -> projects.recordRuntimeProfile(other, body, Optional.of("k1"), "UI")).isInstanceOfSatisfying(
                ApiProblemException.class, e -> assertThat(e.kind()).isEqualTo(ProblemKind.IDEMPOTENCY_CONFLICT));
    }

    @Test
    void consentsAreGrantedRevokedWithTheVersionAndListed() {
        UUID projectId = project().id();

        var granted = projects.grantConsent(projectId, new ConsentGrantInput("WAREHOUSE_ANALYTICS", 1), Optional.empty(), Optional.empty(), "UI");
        ConsentDto revoked = projects.revokeConsent(projectId, "WAREHOUSE_ANALYTICS", granted.body().version(), "UI");

        assertThat(granted.created()).isTrue();
        assertThat(granted.body().revokedAt()).isNull();
        assertThat(revoked.revokedAt()).isNotNull();
        assertThat(projects.consents(projectId).items()).containsExactly(revoked);
        assertThatThrownBy(() -> projects.revokeConsent(projectId, "MODEL_TRAINING", 0, "UI")).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind()).isEqualTo(ProblemKind.NOT_FOUND));
        assertThat(projects.latestPrivacyNotice().version()).isEqualTo(1);
    }

    // ------------------------------------------------------------------ scans and plans

    private record Completed(UUID projectId, ScanDto scan, List<UUID> findingIds) {
    }

    private Completed completedScan() {
        UUID projectId = project().id();
        projects.grantConsent(projectId, new ConsentGrantInput("WAREHOUSE_ANALYTICS", 1), Optional.empty(), Optional.empty(), "UI");
        ScanDto scan = scans.start(projectId, Optional.empty(), "UI");
        FindingBatchResultDto batch = scans.recordFindings(scan.id(), new FindingBatchInput(List.of(finding("Tls#a"), finding("Tls#b"))),
                Optional.empty(), "UI");
        ScanDto done = scans.complete(scan.id(), new ScanCompletionInput("COMPLETED"), Optional.empty(), "UI");
        return new Completed(projectId, done, batch.createdIds());
    }

    @Test
    void findingsAreRecordedFilteredAndSummarized() {
        UUID projectId = project().id();
        ScanDto scan = scans.start(projectId, Optional.empty(), "UI");

        FindingBatchResultDto batch = scans.recordFindings(scan.id(), new FindingBatchInput(List.of(finding("Tls#a"))), Optional.empty(), "UI");

        assertThat(scan.status()).isEqualTo("RUNNING");
        assertThat(scan.completedAt()).isNull();
        assertThat(batch.createdCount()).isEqualTo(1);
        assertThat(scans.findings(scan.id(), "P1", null, null, null, null, 0, 10).items()).hasSize(1);
        assertThat(scans.findings(scan.id(), "P3", null, null, null, null, 0, 10).items()).isEmpty();
        assertThat(scans.finding(batch.createdIds().get(0)).keySizeBits()).isEqualTo(2048);
        assertThat(scans.summary(scan.id()).countsByPriority()).containsEntry("P1", 1);
        assertThatThrownBy(() -> scans.artifact(scan.id())).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind()).isEqualTo(ProblemKind.NOT_FOUND));
    }

    @Test
    void aPlanIsCreatedTransitionedAndRefusedOnAStaleVersionOrAnInvalidMove() {
        Completed run = completedScan();
        PlanInput input = new PlanInput(run.findingIds().stream()
                .map(id -> new PlanItemInputDto(id, 0.7, List.of(new RiskFactorDto("algorithm_weakness", new BigDecimal("0.4"))))).toList());

        var plan = plans.create(run.scan().id(), input, Optional.empty(), "UI");
        PlanItemDto item = plans.get(run.scan().id(), null, 0, 10).items().get(0);
        PlanItemDto approved = plans.transition(item.id(), new PlanItemTransitionInput("APPROVED"), item.version(), Optional.empty(), "UI");

        assertThat(plan.itemCount()).isEqualTo(2);
        assertThat(approved.state()).isEqualTo("APPROVED");
        assertThat(approved.version()).isEqualTo(item.version() + 1);
        assertThatThrownBy(() -> plans.transition(item.id(), new PlanItemTransitionInput("APPLIED"), item.version(), Optional.empty(), "UI"))
                .isInstanceOfSatisfying(ApiProblemException.class, e -> assertThat(e.kind()).isEqualTo(ProblemKind.CONCURRENT_MODIFICATION));
        assertThatThrownBy(() -> plans.transition(item.id(), new PlanItemTransitionInput("VERIFIED"), approved.version(), Optional.empty(), "UI"))
                .isInstanceOfSatisfying(ApiProblemException.class, e -> assertThat(e.kind()).isEqualTo(ProblemKind.INVALID_STATE_TRANSITION));
        assertThatThrownBy(() -> plans.create(run.scan().id(), input, Optional.empty(), "UI")).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind()).isEqualTo(ProblemKind.PLAN_ALREADY_EXISTS));
    }

    @Test
    void theReportIsMarkdownInTurkishUnlessEnglishIsAsked() {
        Completed run = completedScan();
        plans.create(run.scan().id(), new PlanInput(run.findingIds().stream()
                .map(id -> new PlanItemInputDto(id, 0.7, List.of())).toList()), Optional.empty(), "UI");

        String tr = plans.report(run.scan().id(), null);
        String en = plans.report(run.scan().id(), "en-US,en;q=0.9");

        assertThat(tr).startsWith("# Quancrypt geçiş planı raporu").contains("## 1. Özet");
        assertThat(en).startsWith("# Quancrypt migration plan report").contains("## 1. Summary");
        assertThat(plans.report(run.scan().id(), "de")).isEqualTo(tr);
        assertThatThrownBy(() -> plans.report(UUID.randomUUID(), null)).isInstanceOfSatisfying(ApiProblemException.class,
                e -> assertThat(e.kind()).isEqualTo(ProblemKind.NOT_FOUND));
    }
}
