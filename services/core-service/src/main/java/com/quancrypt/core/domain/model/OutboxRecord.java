package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/** A pending or sent outbox row; the payload is the inner event payload only, the envelope is built at relay (D-142). */
public record OutboxRecord(
        UUID id, EventType type, int schemaVersion, ProjectKey projectKey, Instant occurredAt, Map<String, Object> payload) {

    public OutboxRecord {
        payload = java.util.Collections.unmodifiableMap(new java.util.LinkedHashMap<>(payload));
    }
}
