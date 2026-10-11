package com.quancrypt.core.facade.dto;

/** Result of a relay run (schema RelayResult). */
public record RelayCountsDto(int relayedCount, long remainingCount) {
}
