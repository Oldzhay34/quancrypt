package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PlanReportView;

/** Reads the model of the plan report. */
public interface GetPlanReportUseCase {

    PlanReportView execute(GetPlanReportQuery input);
}
