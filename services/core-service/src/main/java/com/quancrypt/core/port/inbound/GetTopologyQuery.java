package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads a scan's topology. */
public record GetTopologyQuery(UUID scanId) {
}
