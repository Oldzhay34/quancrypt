package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.OutboxRecord;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

/** Reads and marks outbox events for the relay. */
public interface OutboxRelayRepository {

    /** Locks up to limit unsent events, oldest first, skipping rows other relays hold. */
    List<OutboxRecord> lockPending(int limit);

    void markPublished(Collection<UUID> ids, Instant at);

    long countPending();
}
