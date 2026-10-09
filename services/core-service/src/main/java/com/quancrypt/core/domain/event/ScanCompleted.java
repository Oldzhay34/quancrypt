package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.Priority;
import java.util.Map;
import java.util.Optional;

/** A scan finished successfully (CompleteScan with outcome COMPLETED). */
public record ScanCompleted(
        int findingCount,
        Map<Priority, Integer> priorityCounts,
        Optional<String> javaVersion,
        Optional<String> springBootVersion,
        long durationSeconds) implements DomainEvent {

    public ScanCompleted {
        priorityCounts = Map.copyOf(priorityCounts);
    }

    @Override
    public EventType type() {
        return EventType.SCAN_COMPLETED;
    }

    @Override
    public Map<String, Object> payload() {
        return Payloads.of(
                "finding_count", findingCount,
                "priority_counts", Payloads.counts(priorityCounts),
                "java_version", Payloads.orNull(javaVersion),
                "spring_boot_version", Payloads.orNull(springBootVersion),
                "duration_seconds", durationSeconds);
    }
}
