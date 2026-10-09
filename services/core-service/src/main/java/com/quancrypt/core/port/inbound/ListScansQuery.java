package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Lists a project's scans, newest first. */
public record ListScansQuery(UUID projectId, int page, int size) {
}
