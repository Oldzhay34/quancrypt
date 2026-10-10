package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** OutboxWriter and OutboxRelayRepository. */
public abstract class OutboxPortsContract extends PortContract {

    private OutboxRecord record(EventType type, ProjectKey key, int second, Map<String, Object> payload) {
        return new OutboxRecord(ids.next(), type, 1, key, at(second), payload);
    }

    @Test
    void pendingEventsAreLockedOldestFirstAndMarkedPublished() {
        ProjectKey key = randomKey();
        OutboxRecord later = record(EventType.SCAN_COMPLETED, key, 5, Map.of("finding_count", 2));
        OutboxRecord earlier = record(EventType.FINDING_DETECTED, key, 1, Map.of("priority", "P1"));
        ports.outboxWriter().append(later);
        ports.outboxWriter().append(earlier);

        assertThat(ports.outboxRelay().lockPending(1)).containsExactly(earlier);
        assertThat(ports.outboxRelay().lockPending(10)).containsExactly(earlier, later);

        ports.outboxRelay().markPublished(List.of(earlier.id()), at(6));

        assertThat(ports.outboxRelay().lockPending(10)).containsExactly(later);
        assertThat(ports.outboxRelay().countPending()).isEqualTo(1);
    }

    @Test
    void payloadWithNestedValuesAndNullsRoundTrips() {
        Map<String, Object> previous = new LinkedHashMap<>();
        previous.put("java_version", "17");
        previous.put("spring_boot_version", null);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("previous", previous);
        payload.put("current", Map.of("java_version", "21", "spring_boot_version", "4.1.1"));
        payload.put("links", List.of(Map.of("protocol", "HTTP", "tls", true, "mtls", false)));
        payload.put("confidence", 0.9);
        payload.put("count", 3);
        OutboxRecord record = record(EventType.PROJECT_RUNTIME_CHANGED, randomKey(), 1, payload);

        ports.outboxWriter().append(record);

        assertThat(ports.outboxRelay().lockPending(10)).containsExactly(record);
    }

    @Test
    void deletingPendingEventsKeepsRevocationsPublishedEventsAndOtherProjects() {
        ProjectKey key = randomKey();
        ProjectKey otherKey = randomKey();
        OutboxRecord published = record(EventType.FINDING_DETECTED, key, 1, Map.of("priority", "P1"));
        OutboxRecord pending = record(EventType.SCAN_COMPLETED, key, 2, Map.of("finding_count", 1));
        OutboxRecord revocation = record(EventType.CONSENT_REVOKED, key, 3, Map.of("consent_type", "WAREHOUSE_ANALYTICS", "delete_requested", false));
        OutboxRecord other = record(EventType.SCAN_COMPLETED, otherKey, 4, Map.of("finding_count", 0));
        for (OutboxRecord r : List.of(published, pending, revocation, other)) {
            ports.outboxWriter().append(r);
        }
        ports.outboxRelay().markPublished(List.of(published.id()), at(5));

        assertThat(ports.outboxWriter().deletePendingExceptRevocations(key)).isEqualTo(1);
        assertThat(ports.outboxRelay().lockPending(10)).containsExactly(revocation, other);
    }
}
