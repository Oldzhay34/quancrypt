package com.quancrypt.core.infrastructure.persistence.idempotency;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.IdempotencyRecord;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.IdempotencyStore;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * Idempotency records (D-144): the first statement of a command inserts a provisional record (status 202) with
 * ON CONFLICT DO NOTHING. A concurrent request with the same key waits on the primary key until the first commits or
 * rolls back, then reads the committed record: the same digest is a replay, a different one a conflict.
 */
public final class JdbcIdempotencyStore implements IdempotencyStore {

    static final int PROVISIONAL_STATUS = 202;

    private final JdbcClient jdbc;

    public JdbcIdempotencyStore(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Begin begin(String key, AuditAction operation, String requestDigest, Instant now) {
        int inserted = jdbc.sql("""
                INSERT INTO idempotency_record (idempotency_key, operation_code, request_sha256, status_code, resource_id, created_at)
                VALUES (:key, :operation, :digest, :status, NULL, :createdAt)
                ON CONFLICT (idempotency_key, operation_code) DO NOTHING""")
                .param("key", key).param("operation", operation.name()).param("digest", requestDigest)
                .param("status", PROVISIONAL_STATUS).param("createdAt", Sql.ts(now))
                .update();
        if (inserted == 1) {
            return new Begin.Fresh();
        }
        IdempotencyRecord stored = jdbc.sql("""
                SELECT idempotency_key, operation_code, request_sha256, status_code, resource_id, created_at
                FROM idempotency_record WHERE idempotency_key = :key AND operation_code = :operation""")
                .param("key", key).param("operation", operation.name())
                .query((rs, n) -> new IdempotencyRecord(rs.getString("idempotency_key"), Sql.code(rs, "operation_code", AuditAction.class),
                        rs.getString("request_sha256"), rs.getInt("status_code"), Sql.optUuid(rs, "resource_id"),
                        Sql.instant(rs, "created_at")))
                .single();
        return stored.requestDigest().equals(requestDigest) ? new Begin.Replay(stored) : new Begin.Conflict();
    }

    @Override
    public void complete(String key, AuditAction operation, int statusCode, Optional<UUID> resourceId) {
        jdbc.sql("""
                UPDATE idempotency_record SET status_code = :status, resource_id = :resourceId
                WHERE idempotency_key = :key AND operation_code = :operation""")
                .param("status", statusCode).param("resourceId", resourceId.orElse(null))
                .param("key", key).param("operation", operation.name())
                .update();
    }

    @Override
    public int deleteOlderThan(Instant cutoff) {
        return jdbc.sql("DELETE FROM idempotency_record WHERE created_at < :cutoff").param("cutoff", Sql.ts(cutoff)).update();
    }
}
