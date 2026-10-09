package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.PlanCreated;
import com.quancrypt.core.domain.exception.NoStrategyException;
import com.quancrypt.core.domain.exception.PlanAlreadyExistsException;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemTransition;
import com.quancrypt.core.domain.model.RiskFactor;
import com.quancrypt.core.domain.model.RiskScore;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.service.PlannedStrategy;
import com.quancrypt.core.domain.service.StrategyPlanner;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.CreatePlanUseCase;
import com.quancrypt.core.port.inbound.PlanItemInput;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RiskFactorInput;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.FindingContext;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.PlanReader;
import com.quancrypt.core.port.outbound.PlanWriter;
import com.quancrypt.core.port.outbound.PlanningContextReader;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Creates the plan of a completed scan: a strategy, effort and risk for every finding (D-124, D-133, D-138). */
public final class CreatePlanService implements CreatePlanUseCase {

    static final int MAX_ITEMS = 500;
    static final int MAX_RISK_FACTORS = 10;

    private final TransactionRunner tx;
    private final ScanAccess access;
    private final FindingReader findingReader;
    private final PlanningContextReader contexts;
    private final RuntimeProfileReader profiles;
    private final StrategyPlanner planner;
    private final PlanReader planReader;
    private final PlanWriter planWriter;
    private final EventRecorder events;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;
    private final IdGenerator ids;

    public CreatePlanService(
            TransactionRunner tx, ScanAccess access, FindingReader findingReader, PlanningContextReader contexts,
            RuntimeProfileReader profiles, StrategyPlanner planner, PlanReader planReader, PlanWriter planWriter,
            EventRecorder events, IdempotentExecutor idempotency, AuditRecorder audit, Clock clock, IdGenerator ids) {
        this.tx = tx;
        this.access = access;
        this.findingReader = findingReader;
        this.contexts = contexts;
        this.profiles = profiles;
        this.planner = planner;
        this.planReader = planReader;
        this.planWriter = planWriter;
        this.events = events;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
        this.ids = ids;
    }

    @Override
    public PlanView execute(CreatePlanCommand input) {
        if (input.items().isEmpty() || input.items().size() > MAX_ITEMS) {
            throw Fail.validation("a plan holds 1.." + MAX_ITEMS + " items");
        }
        CallerKind caller = Codes.caller(input.caller());
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.PLAN_CREATED,
                replay -> planReader.byScan(input.scanId())
                        .map(p -> ViewMapper.plan(p, planReader.allItems(p.id()).size()))
                        .orElseThrow(() -> Fail.notFound("plan")),
                () -> {
                    LockedScan locked = access.completedForShare(input.scanId());
                    UUID scanId = locked.scan().id();
                    if (planReader.byScan(scanId).isPresent()) {
                        throw Fail.problem(ProblemCode.PLAN_ALREADY_EXISTS, "the scan already has a plan");
                    }
                    List<FindingDetail> findings = findingReader.listByScan(scanId);
                    Map<UUID, PlanItemInput> assessments = assessmentsByFinding(input.items(), findings);
                    Map<UUID, FindingContext> context = contexts.load(scanId);
                    Optional<JavaVersion> java = locked.scan().runtimeProfileSequenceNo()
                            .flatMap(seq -> profiles.bySequence(locked.project().id(), seq)).flatMap(RuntimeProfile::java);
                    Instant now = clock.now();
                    Plan plan = new Plan(ids.next(), scanId, now);
                    List<PlanItem> items = new ArrayList<>();
                    List<PlanItemTransition> transitions = new ArrayList<>();
                    for (FindingDetail detail : findings) {
                        Finding finding = detail.finding();
                        FindingContext fc = context.getOrDefault(finding.id(), new FindingContext(false, 0));
                        FindingFacts facts = new FindingFacts(
                                finding.cryptoUsage(detail.file().locationKind()), finding.priority(), fc.onDeviceLink(), fc.callSiteCount(), java);
                        PlannedStrategy planned = plannedStrategy(facts);
                        PlanItemInput assessment = assessments.get(finding.id());
                        PlanItem discovered = PlanItem.discovered(ids.next(), plan.id(), finding.id(), planned.code(), planned.effort(),
                                Guard.valid(() -> RiskScore.of(assessment.riskScore())), riskFactors(assessment));
                        PlanItem planItem = discovered.transitionTo(PlanItemStateCode.PLANNED);
                        items.add(planItem);
                        transitions.add(new PlanItemTransition(
                                ids.next(), planItem.id(), PlanItemStateCode.DISCOVERED, PlanItemStateCode.PLANNED, now, caller));
                    }
                    try {
                        planWriter.insert(plan);
                    } catch (PlanAlreadyExistsException e) {
                        throw Fail.problem(ProblemCode.PLAN_ALREADY_EXISTS, "the scan already has a plan");
                    }
                    planWriter.insertItems(items, transitions);
                    events.recordIfConsented(locked.warehouseConsent(), locked.project().key(),
                            new PlanCreated(items.size(), countBy(items, PlanItem::strategy), countBy(items, PlanItem::effort)));
                    audit.record(AuditAction.PLAN_CREATED, Optional.of(locked.project().key()), Optional.of(plan.id()), caller);
                    return new IdempotentExecutor.Outcome<>(ViewMapper.plan(plan, items.size()), 201, Optional.of(plan.id()));
                }));
    }

    private PlannedStrategy plannedStrategy(FindingFacts facts) {
        try {
            return planner.plan(facts);
        } catch (NoStrategyException e) {
            throw Fail.validation("a finding cannot be planned: " + e.getMessage());
        }
    }

    private static Map<UUID, PlanItemInput> assessmentsByFinding(List<PlanItemInput> items, List<FindingDetail> findings) {
        Map<UUID, PlanItemInput> byFinding = new HashMap<>();
        for (PlanItemInput item : items) {
            if (byFinding.put(item.findingId(), item) != null) {
                throw Fail.validation("a finding is assessed once");
            }
        }
        Set<UUID> expected = findings.stream().map(d -> d.finding().id()).collect(Collectors.toSet());
        if (!expected.equals(byFinding.keySet())) {
            throw Fail.validation("the plan must assess exactly the findings of the scan");
        }
        return byFinding;
    }

    private static List<RiskFactor> riskFactors(PlanItemInput assessment) {
        if (assessment.riskFactors().size() > MAX_RISK_FACTORS) {
            throw Fail.validation("an item holds at most " + MAX_RISK_FACTORS + " risk factors");
        }
        List<RiskFactor> factors = new ArrayList<>();
        for (RiskFactorInput in : assessment.riskFactors()) {
            factors.add(Guard.valid(() -> new RiskFactor(factors.size() + 1, in.featureName(), in.shapValue())));
        }
        return factors;
    }

    private static <K extends Enum<K>> Map<K, Integer> countBy(List<PlanItem> items, Function<PlanItem, K> key) {
        Map<K, Integer> counts = new HashMap<>();
        items.forEach(i -> counts.merge(key.apply(i), 1, Integer::sum));
        return counts;
    }
}
