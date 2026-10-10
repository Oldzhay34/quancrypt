package com.quancrypt.core.facade.dto;

/** Result of one relay run as the driving adapters see it. */
public record RelayOutcome(int relayedCount, long remainingCount, boolean publishFailed) {
}
