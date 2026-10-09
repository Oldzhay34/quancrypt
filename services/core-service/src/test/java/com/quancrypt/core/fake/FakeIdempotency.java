package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.IdempotencyRecord;
import com.quancrypt.core.port.outbound.IdempotencyStore;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Idempotency records keyed by (key, operation) as in the table. */
public final class FakeIdempotency implements IdempotencyStore {

    private final InMemoryDatabase db;

    public FakeIdempotency(InMemoryDatabase db) {
        this.db = db;
    }

    private static String id(String key, AuditAction operation) {
        return operation + "|" + key;
    }

    @Override
    public Begin begin(String key, AuditAction operation, String requestDigest, Instant now) {
        db.lockLog.add("idempotency:begin");
        IdempotencyRecord stored = db.idempotency.get(id(key, operation));
        if (stored == null) {
            db.idempotency.put(id(key, operation), new IdempotencyRecord(key, operation, requestDigest, 202, Optional.empty(), now));
            return new Begin.Fresh();
        }
        return stored.requestDigest().equals(requestDigest) ? new Begin.Replay(stored) : new Begin.Conflict();
    }

    @Override
    public void complete(String key, AuditAction operation, int statusCode, Optional<UUID> resourceId) {
        IdempotencyRecord stored = db.idempotency.get(id(key, operation));
        db.idempotency.put(id(key, operation),
                new IdempotencyRecord(key, operation, stored.requestDigest(), statusCode, resourceId, stored.createdAt()));
    }

    @Override
    public int deleteOlderThan(Instant cutoff) {
        List<String> doomed = db.idempotency.entrySet().stream().filter(e -> e.getValue().createdAt().isBefore(cutoff)).map(Map.Entry::getKey).toList();
        doomed.forEach(db.idempotency::remove);
        return doomed.size();
    }
}
