package com.quancrypt.core.port.inbound;

import java.util.Optional;

/** One finding of a batch. */
public record FindingInput(String path, String symbol, String algorithmFamily, String usageContext, String locationKind, String priority, Optional<Integer> keySizeBits, Optional<Integer> lineStart, Optional<Integer> lineEnd, double confidence, String classifiedBy) {
}
