package com.quancrypt.core.port.inbound.view;

/** A plan with one page of its items. */
public record PlanPageView(PlanView plan, PageView<PlanItemView> items) {
}
