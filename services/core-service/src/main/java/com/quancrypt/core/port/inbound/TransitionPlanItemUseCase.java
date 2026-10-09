package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PlanItemView;

/** Moves a plan item to another state. */
public interface TransitionPlanItemUseCase {

    PlanItemView execute(TransitionPlanItemCommand input);
}
