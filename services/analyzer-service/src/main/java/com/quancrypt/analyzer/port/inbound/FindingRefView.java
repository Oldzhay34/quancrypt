package com.quancrypt.analyzer.port.inbound;

import java.util.Optional;

/** The natural key of a finding an edge refers to (D-208). */
public record FindingRefView(String file, String symbol, String algorithmFamily, String usageContext, Optional<Integer> lineStart) {
}
