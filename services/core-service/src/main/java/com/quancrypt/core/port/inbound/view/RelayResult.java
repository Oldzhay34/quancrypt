package com.quancrypt.core.port.inbound.view;

/** Outcome of one outbox relay run. */
public record RelayResult(int relayedCount, long remainingCount, boolean publishFailed) {
}
