package com.quancrypt.core.infrastructure.outbox;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.OutboxWriter;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Writes outbox events in the caller's transaction (Transactional Outbox, D-20); the payload is already anonymized. */
public final class JdbcOutboxWriter implements OutboxWriter {

    private final JdbcClient jdbc;
    private final OutboxJson json;

    public JdbcOutboxWriter(JdbcClient jdbc, OutboxJson json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Override
    public void append(OutboxRecord record) {
        jdbc.sql("""
                INSERT INTO outbox_event (id, event_type, schema_version, project_key, occurred_at, payload, published_at)
                VALUES (:id, :type, :schemaVersion, :projectKey, :occurredAt, CAST(:payload AS jsonb), NULL)""")
                .param("id", record.id())
                .param("type", record.type().code())
                .param("schemaVersion", record.schemaVersion())
                .param("projectKey", record.projectKey().value())
                .param("occurredAt", Sql.ts(record.occurredAt()))
                .param("payload", json.payload(record.payload()))
                .update();
    }

    /** Pending consent_revoked events are kept so an earlier revocation notice is not lost (D-147). */
    @Override
    public int deletePendingExceptRevocations(ProjectKey projectKey) {
        return jdbc.sql("""
                DELETE FROM outbox_event
                WHERE project_key = :projectKey AND published_at IS NULL AND event_type <> :revoked""")
                .param("projectKey", projectKey.value())
                .param("revoked", EventType.CONSENT_REVOKED.code())
                .update();
    }
}
