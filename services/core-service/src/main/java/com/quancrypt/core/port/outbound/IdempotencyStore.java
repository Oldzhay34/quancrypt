package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.IdempotencyRecord;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** Remembers command results by Idempotency-Key (D-144). */
public interface IdempotencyStore {

    /** Result of {@link #begin}. */
    sealed interface Begin {

        /** No earlier request: a provisional record now exists in this transaction. */
        record Fresh() implements Begin {
        }

        /** The same request ran before: its record. */
        record Replay(IdempotencyRecord record) implements Begin {
        }

        /** The key was used with a different request. */
        record Conflict() implements Begin {
        }
    }

    Begin begin(String key, AuditAction operation, String requestDigest, Instant now);

    void complete(String key, AuditAction operation, int statusCode, Optional<UUID> resourceId);

    /** Deletes records created before the cutoff; returns how many. */
    int deleteOlderThan(Instant cutoff);
}
