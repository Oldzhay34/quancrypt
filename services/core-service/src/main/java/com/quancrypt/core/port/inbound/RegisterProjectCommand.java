package com.quancrypt.core.port.inbound;

import java.util.Optional;

/** Registers a project by its normalized identity; only the HMAC is stored. The use case builds the idempotency digest itself from the HMAC (D-136). */
public record RegisterProjectCommand(String identity, String displayName, Optional<String> idempotencyKey, String caller) {
}
