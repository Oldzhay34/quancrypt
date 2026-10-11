package com.quancrypt.core.facade.dto;

import java.util.List;
import java.util.UUID;

/** Result of a finding batch (schema FindingBatchResult). */
public record FindingBatchResultDto(int createdCount, int existingCount, List<UUID> createdIds) {

    public FindingBatchResultDto {
        createdIds = createdIds == null ? null : List.copyOf(createdIds);
    }
}

