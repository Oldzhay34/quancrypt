package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Reads a scan's plan and one page of its items. */
public record GetPlanQuery(UUID scanId, Optional<String> state, int page, int size) {
}
