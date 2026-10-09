package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Records the project's Java and Spring Boot version. */
public record RecordRuntimeProfileCommand(UUID projectId, String javaVersion, Optional<String> springBootVersion, Optional<Idempotency> idempotency, String caller) {
}
