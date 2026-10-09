package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PlanPageView;

/** Reads a plan and one page of its items. */
public interface GetPlanUseCase {

    PlanPageView execute(GetPlanQuery input);
}
