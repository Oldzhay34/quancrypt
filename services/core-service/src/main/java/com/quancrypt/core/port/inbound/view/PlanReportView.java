package com.quancrypt.core.port.inbound.view;

import java.util.List;
import java.util.Optional;

/** The model of the plan report; the facade renders it as Markdown. */
public record PlanReportView(
        PlanView plan, ScanView scan, Optional<RuntimeProfileView> runtimeProfile, List<ClarificationAnswerView> answers,
        List<PlanReportItemView> items) {

    public PlanReportView {
        answers = List.copyOf(answers);
        items = List.copyOf(items);
    }
}
