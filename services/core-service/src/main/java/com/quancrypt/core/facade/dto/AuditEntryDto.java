package com.quancrypt.core.facade.dto;

import java.time.Instant;
import java.util.UUID;

/** Audit entry (schema AuditEntry). */
public record AuditEntryDto(UUID id, Instant occurredAt, String action, String projectKey, UUID subjectId, String callerKind) {
}
