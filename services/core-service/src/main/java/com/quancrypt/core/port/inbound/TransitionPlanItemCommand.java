package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Moves a plan item to another state. */
public record TransitionPlanItemCommand(UUID itemId, String toState, int expectedVersion, Optional<Idempotency> idempotency, String caller) {
}
