package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads a project. */
public record GetProjectQuery(UUID projectId) {
}
