package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Finishes a scan as COMPLETED or FAILED. */
public record CompleteScanCommand(UUID scanId, String outcome, Optional<Idempotency> idempotency, String caller) {
}
