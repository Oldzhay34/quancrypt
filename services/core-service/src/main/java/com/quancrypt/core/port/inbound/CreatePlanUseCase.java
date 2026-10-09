package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PlanView;

/** Creates the plan of a completed scan. */
public interface CreatePlanUseCase {

    PlanView execute(CreatePlanCommand input);
}
