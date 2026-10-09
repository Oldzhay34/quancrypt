package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** An audit log row: no personal data and no free text (D-125); the project key is empty only for system actions. */
public record AuditEntry(
        UUID id, Instant occurredAt, AuditAction action, Optional<ProjectKey> projectKey, Optional<UUID> subjectId, CallerKind caller) {

    public AuditEntry {
        if (projectKey.isEmpty() && action != AuditAction.OUTBOX_EVENTS_RELAYED) {
            throw new IllegalArgumentException("only the relay action may omit the project key");
        }
    }
}
