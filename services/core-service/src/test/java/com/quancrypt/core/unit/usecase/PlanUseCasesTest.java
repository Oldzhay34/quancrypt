package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.GetPlanQuery;
import com.quancrypt.core.port.inbound.GetPlanReportQuery;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.PlanItemInput;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RiskFactorInput;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import com.quancrypt.core.port.inbound.view.PlanItemView;
import com.quancrypt.core.port.inbound.view.PlanPageView;
import com.quancrypt.core.port.inbound.view.PlanReportItemView;
import com.quancrypt.core.port.inbound.view.PlanReportView;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.inbound.view.RiskFactorView;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

import static com.quancrypt.core.fake.Problems.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

class PlanUseCasesTest {

    private final World w = new World();

    private record Scenario(UUID projectId, UUID scanId, Map<String, UUID> findings) {
    }

    /** A small QBank: two TLS clients (one on a device link), a weak signature, a token and an RSA encryption. */
    private Scenario completedScan(String javaVersion) {
        UUID projectId = w.projectWithWarehouseConsent();
        w.recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, javaVersion, Optional.empty(), Optional.empty(), "UI"));
        UUID scanId = w.runningScan(projectId);
        w.record(scanId,
                World.tlsFinding("gateway/Client.java", "Client#call"),
                World.tlsFinding("device/publisher.py", "Publisher#connect"),
                World.finding("account/Receipt.java", "Receipt#sign", "SHA1", "SIGNATURE", "CODE", "P0", null),
                World.finding("account/Token.java", "Token#issue", "RSA", "TOKEN_SIGNATURE", "CODE", "P3", 2048),
                World.finding("payment/Card.java", "Card#tokenize", "RSA", "ENCRYPTION", "CODE", "P1", 2048));
        Map<String, UUID> byName = new HashMap<>();
        w.db.findings.values().forEach(f -> byName.put(f.symbol(), f.id()));
        List<CallSiteInput> fiveSites = IntStream.range(1, 6).mapToObj(i -> new CallSiteInput("gateway/Client.java", i, i, "CODE")).toList();
        w.recordTopology.execute(new RecordTopologyCommand(scanId,
                List.of(new NodeInput("gateway", "GATEWAY"), new NodeInput("account", "SERVICE"), new NodeInput("broker", "BROKER"), new NodeInput("terminal", "DEVICE")),
                List.of(new LinkInput("gateway", "account", "HTTP", true, true, fiveSites, List.of(byName.get("Client#call"))),
                        new LinkInput("terminal", "broker", "MQTT", true, true, List.of(), List.of(byName.get("Publisher#connect")))),
                "INTERNAL"));
        w.complete(scanId);
        return new Scenario(projectId, scanId, byName);
    }

    private PlanItemView item(Scenario s, String symbol) {
        UUID id = s.findings().get(symbol);
        return w.getPlan.execute(new GetPlanQuery(s.scanId(), Optional.empty(), 0, 50)).items().items().stream()
                .filter(i -> i.findingId().equals(id)).findFirst().orElseThrow();
    }

    @Test
    void aPlanGivesEveryFindingItsStrategyEffortAndRiskAndStartsPlanned() {
        Scenario s = completedScan("25");
        w.db.lockLog.clear();
        PlanView plan = w.plan(s.scanId(), 0.85);
        assertThat(plan.itemCount()).isEqualTo(5);
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:share");
        assertThat(item(s, "Client#call").strategy()).isEqualTo("HYBRID_TLS_KEX");
        assertThat(item(s, "Client#call").effort()).isEqualTo("L");
        assertThat(item(s, "Publisher#connect").strategy()).isEqualTo("DEVICE_HYBRID_TLS");
        assertThat(item(s, "Receipt#sign").strategy()).isEqualTo("FIX_WEAK_CLASSIC");
        assertThat(item(s, "Receipt#sign").effort()).isEqualTo("S");
        assertThat(item(s, "Token#issue").strategy()).isEqualTo("KEEP_SHORT_LIVED_TOKEN");
        assertThat(item(s, "Card#tokenize").strategy()).isEqualTo("KEM_DEM_ENCRYPTION");
        PlanItemView any = item(s, "Token#issue");
        assertThat(any.state()).isEqualTo("PLANNED");
        assertThat(any.version()).isEqualTo(1);
        assertThat(any.riskClass()).isEqualTo("CRITICAL");
        assertThat(any.riskFactors()).extracting(RiskFactorView::rank).containsExactly(1);
        assertThat(w.db.transitions).hasSize(5).allSatisfy(t -> {
            assertThat(t.from()).isEqualTo(PlanItemStateCode.DISCOVERED);
            assertThat(t.to()).isEqualTo(PlanItemStateCode.PLANNED);
        });
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.PLAN_CREATED)).hasSize(1);
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.PLAN_ITEM_TRANSITIONED)).isEmpty();
    }

    @Test
    void theWarehouseGetsOnePlanCreatedEventWithCounts() {
        Scenario s = completedScan("25");
        w.plan(s.scanId(), 0.5);
        OutboxRecord event = w.outbox().stream().filter(r -> r.type() == EventType.PLAN_CREATED).findFirst().orElseThrow();
        assertThat(event.payload()).containsEntry("item_count", 5);
        assertThat(event.payload().get("strategy_counts")).isEqualTo(Map.of("HYBRID_TLS_KEX", 1, "DEVICE_HYBRID_TLS", 1, "FIX_WEAK_CLASSIC", 1,
                "KEEP_SHORT_LIVED_TOKEN", 1, "KEM_DEM_ENCRYPTION", 1));
        assertThat(event.payload().get("effort_counts")).isEqualTo(Map.of("L", 3, "S", 2));
    }

    @Test
    void anOldJavaVersionTurnsTheKemDemItemIntoAJdkUpgrade() {
        Scenario s = completedScan("17.0.2");
        w.plan(s.scanId(), 0.5);
        PlanItemView upgrade = item(s, "Card#tokenize");
        assertThat(upgrade.strategy()).isEqualTo("JDK_UPGRADE");
        assertThat(upgrade.effort()).isEqualTo("M");
        assertThat(item(s, "Client#call").strategy()).isEqualTo("HYBRID_TLS_KEX");
        PlanReportView report = w.getPlanReport.execute(new GetPlanReportQuery(s.scanId()));
        PlanReportItemView row = report.items().stream().filter(r -> r.symbol().equals("Card#tokenize")).findFirst().orElseThrow();
        assertThat(row.replacedStrategy()).hasValue("KEM_DEM_ENCRYPTION");
        assertThat(row.noteCodes()).contains("BOUNCY_CASTLE_ALTERNATIVE");
    }

    @Test
    void aPlanNeedsACompletedScanAndIsCreatedOnce() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID scanId = w.runningScan(projectId);
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        assertProblem(() -> w.plan(scanId, 0.5), ProblemCode.SCAN_NOT_COMPLETED);
        w.complete(scanId);
        w.plan(scanId, 0.5);
        assertProblem(() -> w.plan(scanId, 0.5), ProblemCode.PLAN_ALREADY_EXISTS);
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(new UUID(9, 9), List.of(new PlanItemInput(new UUID(7, 7), 0.5, List.of())),
                Optional.empty(), "UI")), ProblemCode.NOT_FOUND);
    }

    @Test
    void theAssessmentsMustMatchTheFindingsOfTheScanExactly() {
        Scenario s = completedScan("25");
        List<PlanItemInput> all = w.assessAll(s.scanId(), 0.5);
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), all.subList(1, all.size()), Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        List<PlanItemInput> extra = new ArrayList<>(all);
        extra.add(new PlanItemInput(new UUID(9, 9), 0.5, List.of()));
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), extra, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        List<PlanItemInput> duplicate = new ArrayList<>(all.subList(1, all.size()));
        duplicate.add(all.get(1));
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), duplicate, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), List.of(), Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        assertThat(w.db.plans).isEmpty();
    }

    @Test
    void riskInputsAreValidated() {
        Scenario s = completedScan("25");
        List<PlanItemInput> bad = new ArrayList<>(w.assessAll(s.scanId(), 0.5));
        PlanItemInput first = bad.get(0);
        List<RiskFactorInput> eleven = IntStream.range(0, 11).mapToObj(i -> new RiskFactorInput("feature_" + i, BigDecimal.ONE)).toList();
        bad.set(0, new PlanItemInput(first.findingId(), 0.5, eleven));
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), bad, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        bad.set(0, new PlanItemInput(first.findingId(), 1.5, List.of()));
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), bad, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        bad.set(0, new PlanItemInput(first.findingId(), 0.5, List.of(new RiskFactorInput("Bad Name", BigDecimal.ONE))));
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), bad, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        List<PlanItemInput> tooMany = IntStream.range(0, 501).mapToObj(i -> new PlanItemInput(new UUID(7, i), 0.5, List.of())).toList();
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), tooMany, Optional.empty(), "UI")), ProblemCode.VALIDATION_FAILED);
        assertThat(w.db.plans).isEmpty();
    }

    @Test
    void aPlanRetryWithTheSameIdempotencyKeyReplays() {
        Scenario s = completedScan("25");
        CreatePlanCommand command = new CreatePlanCommand(s.scanId(), w.assessAll(s.scanId(), 0.5), World.idem("p1", "d"), "UI");
        PlanView first = w.createPlan.execute(command);
        assertThat(w.createPlan.execute(command).id()).isEqualTo(first.id());
        assertThat(w.db.plans).hasSize(1);
        assertProblem(() -> w.createPlan.execute(new CreatePlanCommand(s.scanId(), w.assessAll(s.scanId(), 0.5), World.idem("p1", "other"), "UI")),
                ProblemCode.IDEMPOTENCY_CONFLICT);
    }

    @Test
    void thePlanIsReadInPagesWithAStateFilterAndDerivedRiskClasses() {
        Scenario s = completedScan("25");
        w.plan(s.scanId(), 0.4);
        PlanPageView page = w.getPlan.execute(new GetPlanQuery(s.scanId(), Optional.empty(), 0, 2));
        assertThat(page.items().items()).hasSize(2);
        assertThat(page.items().total()).isEqualTo(5);
        assertThat(page.plan().itemCount()).isEqualTo(5);
        assertThat(page.items().items()).allSatisfy(i -> assertThat(i.riskClass()).isEqualTo("MEDIUM"));
        assertThat(w.getPlan.execute(new GetPlanQuery(s.scanId(), Optional.of("APPROVED"), 0, 10)).items().total()).isZero();
        assertThat(w.getPlan.execute(new GetPlanQuery(s.scanId(), Optional.of("PLANNED"), 0, 10)).items().total()).isEqualTo(5);
        assertProblem(() -> w.getPlan.execute(new GetPlanQuery(s.scanId(), Optional.of("BOGUS"), 0, 10)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.getPlan.execute(new GetPlanQuery(s.scanId(), Optional.empty(), 0, 0)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.getPlan.execute(new GetPlanQuery(new UUID(9, 9), Optional.empty(), 0, 10)), ProblemCode.NOT_FOUND);
        UUID noPlan = w.runningScan(s.projectId());
        assertProblem(() -> w.getPlan.execute(new GetPlanQuery(noPlan, Optional.empty(), 0, 10)), ProblemCode.NOT_FOUND);
    }

    private PlanItemView transition(UUID itemId, String to, int version) {
        return w.transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, to, version, Optional.empty(), "UI"));
    }

    @Test
    void anItemWalksThroughItsStatesWithTheVersionGrowingAndEventsForTheWarehouse() {
        Scenario s = completedScan("25");
        w.plan(s.scanId(), 0.5);
        UUID itemId = item(s, "Card#tokenize").id();
        w.db.lockLog.clear();
        PlanItemView approved = transition(itemId, "APPROVED", 1);
        assertThat(approved.state()).isEqualTo("APPROVED");
        assertThat(approved.version()).isEqualTo(2);
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share");
        transition(itemId, "APPLIED", 2);
        PlanItemView rolledBack = transition(itemId, "ROLLED_BACK", 3);
        assertThat(rolledBack.version()).isEqualTo(4);
        assertThat(transition(itemId, "PLANNED", 4).state()).isEqualTo("PLANNED");
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.PLAN_ITEM_TRANSITIONED)).hasSize(4);
        assertThat(w.db.transitions.stream().filter(t -> t.planItemId().equals(itemId))).hasSize(5);
        assertThat(w.outboxTypes().stream().filter(t -> t == EventType.PLAN_ITEM_TRANSITIONED)).hasSize(4);
        OutboxRecord first = w.outbox().stream().filter(r -> r.type() == EventType.PLAN_ITEM_TRANSITIONED).findFirst().orElseThrow();
        assertThat(first.payload()).containsEntry("strategy", "KEM_DEM_ENCRYPTION").containsEntry("from_state", "PLANNED").containsEntry("to_state", "APPROVED");
    }

    @Test
    void aForbiddenStaleOrUnknownTransitionIsRefusedAndLeavesTheItemAlone() {
        Scenario s = completedScan("25");
        w.plan(s.scanId(), 0.5);
        UUID itemId = item(s, "Card#tokenize").id();
        assertProblem(() -> transition(itemId, "VERIFIED", 1), ProblemCode.INVALID_STATE_TRANSITION);
        assertProblem(() -> transition(itemId, "PLANNED", 1), ProblemCode.INVALID_STATE_TRANSITION);
        assertProblem(() -> transition(itemId, "APPROVED", 0), ProblemCode.CONCURRENT_MODIFICATION);
        assertProblem(() -> transition(itemId, "NOT_A_STATE", 1), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> transition(new UUID(9, 9), "APPROVED", 1), ProblemCode.NOT_FOUND);
        PlanItemView untouched = item(s, "Card#tokenize");
        assertThat(untouched.state()).isEqualTo("PLANNED");
        assertThat(untouched.version()).isEqualTo(1);
    }

    @Test
    void withoutWarehouseConsentATransitionWritesNoEventButStillAuditsIt() {
        UUID projectId = w.project();
        UUID scanId = w.runningScan(projectId);
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        w.complete(scanId);
        w.plan(scanId, 0.5);
        PlanItemView only = w.getPlan.execute(new GetPlanQuery(scanId, Optional.empty(), 0, 10)).items().items().get(0);
        transition(only.id(), "APPROVED", 1);
        assertThat(w.outbox()).isEmpty();
        assertThat(w.auditActions()).contains(AuditAction.PLAN_ITEM_TRANSITIONED);
    }

    @Test
    void aTransitionRetryWithTheSameIdempotencyKeyReplays() {
        Scenario s = completedScan("25");
        w.plan(s.scanId(), 0.5);
        UUID itemId = item(s, "Card#tokenize").id();
        TransitionPlanItemCommand command = new TransitionPlanItemCommand(itemId, "APPROVED", 1, World.idem("t1", "d"), "UI");
        w.transitionPlanItem.execute(command);
        PlanItemView replay = w.transitionPlanItem.execute(command);
        assertThat(replay.state()).isEqualTo("APPROVED");
        assertThat(replay.version()).isEqualTo(2);
        assertThat(w.db.transitions.stream().filter(t -> t.planItemId().equals(itemId))).hasSize(2);
    }

    @Test
    void theReportListsTheHighestRiskFirstWithItsNotes() {
        Scenario s = completedScan("25");
        List<PlanItemInput> mixed = new ArrayList<>();
        double score = 0.1;
        for (PlanItemInput in : w.assessAll(s.scanId(), 0.0)) {
            mixed.add(new PlanItemInput(in.findingId(), score, in.riskFactors()));
            score += 0.2;
        }
        w.createPlan.execute(new CreatePlanCommand(s.scanId(), mixed, Optional.empty(), "UI"));
        PlanReportView report = w.getPlanReport.execute(new GetPlanReportQuery(s.scanId()));
        assertThat(report.items()).hasSize(5);
        assertThat(report.items()).extracting(PlanReportItemView::riskScore).isSortedAccordingTo(Comparator.reverseOrder());
        assertThat(report.scan().id()).isEqualTo(s.scanId());
        assertThat(report.runtimeProfile()).hasValueSatisfying(p -> assertThat(p.javaVersion()).isEqualTo("25"));
        PlanReportItemView tls = report.items().stream().filter(r -> r.symbol().equals("Client#call")).findFirst().orElseThrow();
        assertThat(tls.noteCodes()).contains("HYBRID_TLS_DEFAULT_ARRIVES_IN_JDK_27");
        assertThat(tls.path()).isEqualTo("gateway/Client.java");
        assertProblem(() -> w.getPlanReport.execute(new GetPlanReportQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
        UUID noPlan = w.runningScan(s.projectId());
        assertProblem(() -> w.getPlanReport.execute(new GetPlanReportQuery(noPlan)), ProblemCode.NOT_FOUND);
    }
}
