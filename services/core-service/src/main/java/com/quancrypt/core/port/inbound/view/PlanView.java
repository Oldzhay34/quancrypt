package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.UUID;

/** A plan. */
public record PlanView(UUID id, UUID scanId, Instant createdAt, int itemCount) {
}
