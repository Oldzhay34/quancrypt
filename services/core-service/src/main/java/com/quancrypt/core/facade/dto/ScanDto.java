package com.quancrypt.core.facade.dto;

import java.time.Instant;
import java.util.UUID;

/** Scan (schema Scan). */
public record ScanDto(UUID id, UUID projectId, String status, Instant startedAt, Instant completedAt, Integer runtimeProfileSequenceNo) {
}
