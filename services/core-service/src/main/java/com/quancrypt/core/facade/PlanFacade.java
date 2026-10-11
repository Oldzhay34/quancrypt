package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.PlanDto;
import com.quancrypt.core.facade.dto.PlanInput;
import com.quancrypt.core.facade.dto.PlanItemDto;
import com.quancrypt.core.facade.dto.PlanItemTransitionInput;
import com.quancrypt.core.facade.dto.PlanPageDto;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.CreatePlanUseCase;
import com.quancrypt.core.port.inbound.GetPlanQuery;
import com.quancrypt.core.port.inbound.GetPlanReportQuery;
import com.quancrypt.core.port.inbound.GetPlanReportUseCase;
import com.quancrypt.core.port.inbound.GetPlanUseCase;
import com.quancrypt.core.port.inbound.PlanItemInput;
import com.quancrypt.core.port.inbound.RiskFactorInput;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemUseCase;
import com.quancrypt.core.port.inbound.view.PlanPageView;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Plans, plan item transitions and the Markdown plan report. */
public final class PlanFacade {

    private final CreatePlanUseCase createPlan;
    private final GetPlanUseCase getPlan;
    private final TransitionPlanItemUseCase transitionPlanItem;
    private final GetPlanReportUseCase getPlanReport;

    public PlanFacade(
            CreatePlanUseCase createPlan, GetPlanUseCase getPlan, TransitionPlanItemUseCase transitionPlanItem,
            GetPlanReportUseCase getPlanReport) {
        this.createPlan = createPlan;
        this.getPlan = getPlan;
        this.transitionPlanItem = transitionPlanItem;
        this.getPlanReport = getPlanReport;
    }

    public PlanDto create(UUID scanId, PlanInput body, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> {
            List<PlanItemInput> items = body.items().stream()
                    .map(i -> new PlanItemInput(i.findingId(), i.riskScore(),
                            i.riskFactors().stream().map(f -> new RiskFactorInput(f.featureName(), f.shapValue())).toList()))
                    .toList();
            return FacadeMapper.plan(createPlan.execute(new CreatePlanCommand(scanId, items,
                    Idem.of(idempotencyKey, "POST", "/api/v1/scans/{scanId}/plan", body, scanId.toString()), caller)));
        });
    }

    public PlanPageDto get(UUID scanId, String state, int page, int size) {
        return ProblemTranslator.call(() -> {
            PlanPageView view = getPlan.execute(new GetPlanQuery(scanId, Optional.ofNullable(state), page, size));
            List<PlanItemDto> items = view.items().items().stream().map(FacadeMapper::planItem).toList();
            return new PlanPageDto(FacadeMapper.plan(view.plan()), items, view.items().page(), view.items().size(), view.items().total());
        });
    }

    public PlanItemDto transition(
            UUID itemId, PlanItemTransitionInput body, int expectedVersion, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> FacadeMapper.planItem(transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, body.toState(),
                expectedVersion, Idem.of(idempotencyKey, "POST", "/api/v1/plan-items/{itemId}/transitions", body, itemId.toString(),
                        String.valueOf(expectedVersion)), caller))));
    }

    /** The Markdown report; acceptLanguage is the raw header value (en, otherwise Turkish). */
    public String report(UUID scanId, String acceptLanguage) {
        return ProblemTranslator.call(() -> new PlanReportRenderer(PlanReportRenderer.Language.of(acceptLanguage))
                .render(getPlanReport.execute(new GetPlanReportQuery(scanId))));
    }
}
