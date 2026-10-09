package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads a project's runtime profile and answers. */
public record GetProjectProfileQuery(UUID projectId) {
}
