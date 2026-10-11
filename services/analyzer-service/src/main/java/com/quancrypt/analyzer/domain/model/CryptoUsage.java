package com.quancrypt.analyzer.domain.model;

import java.util.Objects;
import java.util.Optional;

/** One crypto usage found by a detector (a finding of finding.schema.json). */
public record CryptoUsage(Evidence evidence, String symbol, CryptoAlgorithm algorithm, UsageContext usageContext,
        Priority priority, Optional<String> library, double confidence, String detectorId) {

    public CryptoUsage {
        Objects.requireNonNull(evidence, "evidence");
        Text.printable(symbol, 512, "symbol");
        Objects.requireNonNull(algorithm, "algorithm");
        Objects.requireNonNull(usageContext, "usageContext");
        Objects.requireNonNull(priority, "priority");
        Text.optionalMatching(library, Text.TOKEN, "library");
        if (!(confidence >= 0.0 && confidence <= 1.0)) {
            throw new IllegalArgumentException("confidence must be between 0 and 1");
        }
        Text.matching(detectorId, Text.IDENTIFIER, "detectorId");
    }

    /** Whether the usage was found in test code (kept and marked, D-173). */
    public boolean inTestCode() {
        return evidence.locationKind() == LocationKind.TEST_CODE;
    }
}
