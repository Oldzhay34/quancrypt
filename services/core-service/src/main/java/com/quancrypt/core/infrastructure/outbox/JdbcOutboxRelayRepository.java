package com.quancrypt.core.infrastructure.outbox;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.OutboxRelayRepository;
import java.time.Instant;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** The relay's view of the outbox: oldest unsent events first, rows another relay holds are skipped. */
public final class JdbcOutboxRelayRepository implements OutboxRelayRepository {

    private final JdbcClient jdbc;
    private final OutboxJson json;

    public JdbcOutboxRelayRepository(JdbcClient jdbc, OutboxJson json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Override
    public List<OutboxRecord> lockPending(int limit) {
        return jdbc.sql("""
                SELECT id, event_type, schema_version, project_key, occurred_at, payload::text AS payload
                FROM outbox_event WHERE published_at IS NULL
                ORDER BY occurred_at, id LIMIT :limit
                FOR UPDATE SKIP LOCKED""")
                .param("limit", limit)
                .query((rs, n) -> new OutboxRecord(
                        Sql.uuid(rs, "id"),
                        eventType(rs.getString("event_type")),
                        rs.getInt("schema_version"),
                        new ProjectKey(rs.getString("project_key")),
                        Sql.instant(rs, "occurred_at"),
                        json.payload(rs.getString("payload"))))
                .list();
    }

    @Override
    public void markPublished(Collection<UUID> ids, Instant at) {
        if (ids.isEmpty()) {
            return;
        }
        jdbc.sql("UPDATE outbox_event SET published_at = :at WHERE id = ANY(CAST(:ids AS uuid[])) AND published_at IS NULL")
                .param("at", Sql.ts(at)).param("ids", Sql.textArray(ids)).update();
    }

    @Override
    public long countPending() {
        return jdbc.sql("SELECT count(*) FROM outbox_event WHERE published_at IS NULL").query(Long.class).single();
    }

    static EventType eventType(String code) {
        return Arrays.stream(EventType.values()).filter(t -> t.code().equals(code)).findFirst()
                .orElseThrow(() -> new IllegalStateException("unknown event type in the outbox: " + code));
    }
}
