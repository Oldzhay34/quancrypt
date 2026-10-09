package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** An audit log row. */
public record AuditEntryView(UUID id, Instant occurredAt, String action, Optional<String> projectKey, Optional<UUID> subjectId, String callerKind) {
}
