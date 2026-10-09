package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.exception.NoStrategyException;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
import com.quancrypt.core.domain.service.PlannedStrategy;
import com.quancrypt.core.domain.service.StrategyPlanner;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import com.quancrypt.core.port.inbound.GetPlanReportQuery;
import com.quancrypt.core.port.inbound.GetPlanReportUseCase;
import com.quancrypt.core.port.inbound.view.PlanReportItemView;
import com.quancrypt.core.port.inbound.view.PlanReportView;
import com.quancrypt.core.port.outbound.FindingContext;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.PlanReader;
import com.quancrypt.core.port.outbound.PlanningContextReader;
import com.quancrypt.core.port.outbound.RiskThresholdReader;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/** Builds the model of the plan report; notes are recomputed from the finding facts and rendered by the facade. */
public final class GetPlanReportService implements GetPlanReportUseCase {

    private final TransactionRunner tx;
    private final ScanReader scans;
    private final PlanReader plans;
    private final FindingReader findings;
    private final PlanningContextReader contexts;
    private final RuntimeProfileReader profiles;
    private final RiskThresholdReader thresholds;
    private final StrategyPlanner planner;

    public GetPlanReportService(
            TransactionRunner tx, ScanReader scans, PlanReader plans, FindingReader findings, PlanningContextReader contexts,
            RuntimeProfileReader profiles, RiskThresholdReader thresholds, StrategyPlanner planner) {
        this.tx = tx;
        this.scans = scans;
        this.plans = plans;
        this.findings = findings;
        this.contexts = contexts;
        this.profiles = profiles;
        this.thresholds = thresholds;
        this.planner = planner;
    }

    @Override
    public PlanReportView execute(GetPlanReportQuery input) {
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Scan scan = scans.find(input.scanId()).orElseThrow(() -> Fail.notFound("scan"));
            Plan plan = plans.byScan(scan.id()).orElseThrow(() -> Fail.notFound("plan"));
            Optional<RuntimeProfile> profile = scan.runtimeProfileSequenceNo().flatMap(seq -> profiles.bySequence(scan.projectId(), seq));
            Optional<JavaVersion> java = profile.flatMap(RuntimeProfile::java);
            RiskClassPolicy policy = thresholds.policy();
            Map<UUID, FindingDetail> details = findings.listByScan(scan.id()).stream()
                    .collect(Collectors.toMap(d -> d.finding().id(), d -> d));
            Map<UUID, FindingContext> context = contexts.load(scan.id());
            List<PlanItem> items = plans.allItems(plan.id());
            List<PlanReportItemView> rows = items.stream()
                    .map(item -> row(item, details.get(item.findingId()), context, java, policy))
                    .sorted(Comparator.comparing(PlanReportItemView::riskScore).reversed().thenComparing(PlanReportItemView::path))
                    .toList();
            return new PlanReportView(ViewMapper.plan(plan, items.size()), ViewMapper.scan(scan),
                    profile.map(p -> ViewMapper.runtimeProfile(p, false)), rows);
        });
    }

    private PlanReportItemView row(
            PlanItem item, FindingDetail detail, Map<UUID, FindingContext> context, Optional<JavaVersion> java, RiskClassPolicy policy) {
        FindingContext fc = context.getOrDefault(item.findingId(), new FindingContext(false, 0));
        FindingFacts facts = new FindingFacts(
                detail.finding().cryptoUsage(detail.file().locationKind()), detail.finding().priority(), fc.onDeviceLink(), fc.callSiteCount(), java);
        List<String> notes = List.of();
        Optional<String> replaced = Optional.empty();
        try {
            PlannedStrategy planned = planner.plan(facts);
            if (planned.code() == item.strategy()) {
                notes = planned.notes().stream().map(Enum::name).toList();
                replaced = planned.replacedStrategy().map(Enum::name);
            }
        } catch (NoStrategyException e) {
            // The stored snapshot stays authoritative when the policy changed since the plan was made.
            notes = List.of();
        }
        return new PlanReportItemView(detail.file().path(), detail.finding().symbol(), item.strategy().name(), item.effort().name(),
                item.riskScore().value(), policy.classify(item.riskScore()).name(), item.state().code().name(), notes, replaced,
                ViewMapper.riskFactors(item));
    }
}
