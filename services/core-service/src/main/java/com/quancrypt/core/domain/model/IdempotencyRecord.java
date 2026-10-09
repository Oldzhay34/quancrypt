package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** Remembers the digest, status and resulting resource of a command so a retry gets the same result (D-144). */
public record IdempotencyRecord(
        String key, AuditAction operation, String requestDigest, int statusCode, Optional<UUID> resourceId, Instant createdAt) {

    public IdempotencyRecord {
        if (key == null || key.isBlank() || key.length() > 128) {
            throw new IllegalArgumentException("idempotency key must be 1..128 characters");
        }
    }
}
