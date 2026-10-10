package com.quancrypt.core.infrastructure.outbox;

import com.quancrypt.core.domain.model.OutboxRecord;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/** JSON of outbox payloads (the jsonb column) and of the event envelope sent to the data platform. */
public final class OutboxJson {

    private static final TypeReference<LinkedHashMap<String, Object>> MAP = new TypeReference<>() {
    };

    private final JsonMapper mapper = JsonMapper.builder().build();

    public String payload(Map<String, Object> payload) {
        return mapper.writeValueAsString(payload);
    }

    public Map<String, Object> payload(String json) {
        return mapper.readValue(json, MAP);
    }

    /**
     * The envelope is built from the columns at send time; the stored payload is only the inner event body (D-142).
     * Field names follow contracts/schemas/events.
     */
    public static Map<String, Object> envelope(OutboxRecord record) {
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("event_id", record.id().toString());
        envelope.put("event_type", record.type().code());
        envelope.put("schema_version", record.schemaVersion());
        envelope.put("occurred_at", record.occurredAt().toString());
        envelope.put("project_key", record.projectKey().value());
        envelope.put("payload", record.payload());
        return envelope;
    }

    public String envelopes(List<OutboxRecord> batch) {
        return mapper.writeValueAsString(batch.stream().map(OutboxJson::envelope).toList());
    }
}
