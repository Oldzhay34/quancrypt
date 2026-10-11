package com.quancrypt.analyzer.port.inbound;

import java.util.Optional;

/** One finding as finding.schema.json describes it; codes are the enum names of crypto-domain. */
public record FindingView(String file, Optional<Integer> lineStart, Optional<Integer> lineEnd, String rawName, String symbol,
        String algorithmFamily, Optional<String> mode, Optional<String> padding, Optional<String> hash,
        Optional<Integer> keySizeBits, String usageContext, String locationKind, String priority, Optional<String> library,
        double confidence, String detectorId) {
}
