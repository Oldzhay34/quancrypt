package com.quancrypt.core.facade.dto;

import java.util.UUID;

/** Finding (schema Finding). */
public record FindingDto(UUID id, UUID scanId, String path, String symbol, String algorithmFamily, String usageContext, String locationKind, String priority, Integer keySizeBits, Integer lineStart, Integer lineEnd, double confidence, String classifiedBy) {
}
