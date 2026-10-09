package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
import com.quancrypt.core.port.inbound.GetPlanQuery;
import com.quancrypt.core.port.inbound.GetPlanUseCase;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.PlanItemView;
import com.quancrypt.core.port.inbound.view.PlanPageView;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.PlanReader;
import com.quancrypt.core.port.outbound.RiskThresholdReader;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;

/** Reads a scan's plan with one page of its items; risk classes are derived from the thresholds (D-128). */
public final class GetPlanService implements GetPlanUseCase {

    private final TransactionRunner tx;
    private final ScanReader scans;
    private final PlanReader plans;
    private final RiskThresholdReader thresholds;

    public GetPlanService(TransactionRunner tx, ScanReader scans, PlanReader plans, RiskThresholdReader thresholds) {
        this.tx = tx;
        this.scans = scans;
        this.plans = plans;
        this.thresholds = thresholds;
    }

    @Override
    public PlanPageView execute(GetPlanQuery input) {
        Guard.page(input.page(), input.size());
        Optional<PlanItemStateCode> state = Codes.parseOptional(PlanItemStateCode.class, input.state(), "state");
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            scans.find(input.scanId()).orElseThrow(() -> Fail.notFound("scan"));
            Plan plan = plans.byScan(input.scanId()).orElseThrow(() -> Fail.notFound("plan"));
            RiskClassPolicy policy = thresholds.policy();
            int itemCount = (int) plans.items(plan.id(), Optional.empty(), 0, 1).total();
            PageView<PlanItemView> items = ViewMapper.page(plans.items(plan.id(), state, input.page(), input.size()), i -> ViewMapper.planItem(i, policy));
            return new PlanPageView(ViewMapper.plan(plan, itemCount), items);
        });
    }
}
