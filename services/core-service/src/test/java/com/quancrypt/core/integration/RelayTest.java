package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.view.RelayResult;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/**
 * The relay end to end with the real HttpEventPublisher against a loopback ingest-api stub: delivered events are
 * marked, a failed delivery leaves them pending (D-156), envelopes carry exactly the event schema fields (D-142), and
 * idempotency records older than 24 hours are purged (D-136).
 */
class RelayTest extends IntegrationTest {

    private static final List<String> ENVELOPE_FIELDS = List.of("event_id", "event_type", "schema_version", "occurred_at", "project_key", "payload");

    private UUID projectWithOneEvent() {
        UUID projectId = projectWithConsent("/work/demo");
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.of("4.1.1"), Optional.empty(), "UI"));
        return projectId;
    }

    @Test
    void deliveredEventsAreMarkedAndAudited() {
        projectWithOneEvent();

        RelayResult result = relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));

        assertThat(result.relayedCount()).isEqualTo(1);
        assertThat(result.remainingCount()).isZero();
        assertThat(result.publishFailed()).isFalse();
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE published_at IS NOT NULL").query(Integer.class).single()).isEqualTo(1);
        assertThat(jdbc.sql("SELECT count(*) FROM audit_log WHERE action_code = 'OUTBOX_EVENTS_RELAYED' AND project_key IS NULL")
                .query(Integer.class).single()).isEqualTo(1);
    }

    @Test
    void envelopeHasExactlyTheSchemaFields() {
        projectWithOneEvent();
        String projectKey = jdbc.sql("SELECT project_key FROM project").query(String.class).single();
        UUID eventId = jdbc.sql("SELECT id FROM outbox_event").query(UUID.class).single();

        relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));

        List<Map<String, Object>> sent = JsonMapper.builder().build().readValue(INGEST.bodies().getFirst(), new TypeReference<>() {
        });
        assertThat(sent).hasSize(1);
        Map<String, Object> envelope = sent.getFirst();
        assertThat(envelope).containsOnlyKeys(ENVELOPE_FIELDS);
        assertThat(envelope).containsEntry("event_id", eventId.toString()).containsEntry("event_type", "project_runtime_changed")
                .containsEntry("schema_version", 1).containsEntry("project_key", projectKey);
        assertThat((String) envelope.get("occurred_at")).matches("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z");
        @SuppressWarnings("unchecked")
        Map<String, Object> payload = (Map<String, Object>) envelope.get("payload");
        assertThat(payload).containsOnlyKeys("previous", "current");
        assertThat(payload.get("previous")).isNull();
    }

    @Test
    void failedDeliveryLeavesEventsPendingAndWritesNoAudit() {
        projectWithOneEvent();
        INGEST.answer(503);

        RelayResult result = relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));

        assertThat(result.publishFailed()).isTrue();
        assertThat(result.relayedCount()).isZero();
        assertThat(result.remainingCount()).isEqualTo(1);
        assertThat(jdbc.sql("SELECT count(*) FROM audit_log WHERE action_code = 'OUTBOX_EVENTS_RELAYED'").query(Integer.class).single()).isZero();

        INGEST.answer(202);
        assertThat(relayOutboxEvents.execute(new RelayOutboxEventsCommand(100)).relayedCount()).isEqualTo(1);
    }

    @Test
    void idempotencyRecordsOlderThan24HoursArePurged() {
        jdbc.sql("""
                INSERT INTO idempotency_record (idempotency_key, operation_code, request_sha256, status_code, resource_id, created_at) VALUES
                ('old', 'SCAN_STARTED', repeat('a', 64), 201, NULL, now() - interval '25 hours'),
                ('new', 'SCAN_STARTED', repeat('a', 64), 201, NULL, now() - interval '23 hours')""").update();

        relayOutboxEvents.execute(new RelayOutboxEventsCommand(100));

        assertThat(jdbc.sql("SELECT idempotency_key FROM idempotency_record").query(String.class).list()).containsExactly("new");
        assertThat(rows("audit_log")).isZero();
    }
}
