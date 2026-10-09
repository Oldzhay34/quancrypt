package com.quancrypt.core.port.inbound.view;

import java.util.List;
import java.util.UUID;

/** How many findings of a batch were new. */
public record RecordFindingsResult(int createdCount, int existingCount, List<UUID> createdIds) {

    public RecordFindingsResult {
        createdIds = List.copyOf(createdIds);
    }
}
