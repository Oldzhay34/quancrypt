package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.EventType;
import java.util.Map;
import java.util.Optional;

/** The Java or Spring Boot version of a project changed (RecordRuntimeProfile). */
public record ProjectRuntimeChanged(Optional<Snapshot> previous, Snapshot current) implements DomainEvent {

    /** Java and Spring Boot version at one point in time. */
    public record Snapshot(String javaVersion, Optional<String> springBootVersion) {

        Map<String, Object> payload() {
            return Payloads.of("java_version", javaVersion, "spring_boot_version", Payloads.orNull(springBootVersion));
        }
    }

    @Override
    public EventType type() {
        return EventType.PROJECT_RUNTIME_CHANGED;
    }

    @Override
    public Map<String, Object> payload() {
        return Payloads.of("previous", previous.map(Snapshot::payload).orElse(null), "current", current.payload());
    }
}
