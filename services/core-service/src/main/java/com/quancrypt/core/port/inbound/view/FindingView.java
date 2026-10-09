package com.quancrypt.core.port.inbound.view;

import java.util.Optional;
import java.util.UUID;

/** A finding with its evidence (path and line range). */
public record FindingView(UUID id, UUID scanId, String path, String symbol, String algorithmFamily, String usageContext, String locationKind, String priority, Optional<Integer> keySizeBits, Optional<Integer> lineStart, Optional<Integer> lineEnd, double confidence, String classifiedBy) {
}
