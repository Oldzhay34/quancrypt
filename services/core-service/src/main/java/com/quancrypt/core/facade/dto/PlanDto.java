package com.quancrypt.core.facade.dto;

import java.time.Instant;
import java.util.UUID;

/** Plan (schema Plan). */
public record PlanDto(UUID id, UUID scanId, Instant createdAt, int itemCount) {
}
