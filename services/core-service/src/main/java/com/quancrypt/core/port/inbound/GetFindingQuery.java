package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads one finding. */
public record GetFindingQuery(UUID findingId) {
}
