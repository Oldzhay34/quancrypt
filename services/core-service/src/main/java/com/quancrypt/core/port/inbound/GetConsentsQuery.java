package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Lists a project's consents. */
public record GetConsentsQuery(UUID projectId) {
}
