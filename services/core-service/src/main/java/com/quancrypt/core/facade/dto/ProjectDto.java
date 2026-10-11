package com.quancrypt.core.facade.dto;

import java.time.Instant;
import java.util.UUID;

/** Project (contract schema Project). */
public record ProjectDto(UUID id, String projectKey, String displayName, Instant createdAt) {
}
