package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.UUID;

/** The record of one plan item state change. */
public record PlanItemTransition(
        UUID id, UUID planItemId, PlanItemStateCode from, PlanItemStateCode to, Instant transitionedAt, CallerKind caller) {
}
