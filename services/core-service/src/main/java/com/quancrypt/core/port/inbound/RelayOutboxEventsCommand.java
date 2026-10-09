package com.quancrypt.core.port.inbound;

/** Sends pending outbox events on and purges old idempotency records. */
public record RelayOutboxEventsCommand(int batchSize) {
}
