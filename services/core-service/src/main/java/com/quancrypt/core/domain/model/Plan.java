package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.UUID;

/** The migration plan of a completed scan; one plan per scan. */
public record Plan(UUID id, UUID scanId, Instant createdAt) {
}
