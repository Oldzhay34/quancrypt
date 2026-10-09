package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Lists a scan's findings with optional filters. */
public record ListFindingsQuery(UUID scanId, Optional<String> priority, Optional<String> algorithmFamily, Optional<String> usageContext, Optional<String> locationKind, Optional<String> classifiedBy, int page, int size) {
}
