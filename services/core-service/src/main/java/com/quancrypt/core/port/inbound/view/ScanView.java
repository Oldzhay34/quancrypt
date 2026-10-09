package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** A scan. */
public record ScanView(UUID id, UUID projectId, String status, Instant startedAt, Optional<Instant> completedAt, Optional<Integer> runtimeProfileSequenceNo) {
}
