package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.UUID;

/** A project; created tells a new registration from an existing one. */
public record ProjectView(UUID id, String projectKey, String displayName, Instant createdAt, boolean created) {
}
