package com.quancrypt.analyzer.port.inbound;

import java.util.Optional;

/** Where a node or an edge was seen. */
public record EvidenceView(String file, Optional<Integer> lineStart, Optional<Integer> lineEnd, String locationKind) {
}
