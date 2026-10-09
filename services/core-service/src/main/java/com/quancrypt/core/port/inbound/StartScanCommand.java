package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Starts a scan. */
public record StartScanCommand(UUID projectId, Optional<Idempotency> idempotency, String caller) {
}
