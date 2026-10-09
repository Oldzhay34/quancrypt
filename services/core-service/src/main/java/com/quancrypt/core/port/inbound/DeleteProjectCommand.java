package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Deletes a project and everything under it (KVKK). */
public record DeleteProjectCommand(UUID projectId, String caller) {
}
