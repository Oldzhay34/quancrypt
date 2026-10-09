package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.OutboxRecord;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/** Hands outbox events to the data platform. */
public interface EventPublisher {

    /** Sends the events on; returns the ids the receiver accepted (it deduplicates by event id); throws PublishFailedException when it cannot deliver. */
    Set<UUID> publish(List<OutboxRecord> batch);
}
