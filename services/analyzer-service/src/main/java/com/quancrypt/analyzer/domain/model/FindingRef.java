package com.quancrypt.analyzer.domain.model;

import java.util.Objects;
import java.util.Optional;

/**
 * A finding as an edge refers to it (D-208): the analyzer gives findings no id, so the reference is the natural key
 * core-service keeps findings unique by (file, symbol, algorithm family, usage context, first line); the agent maps it to the
 * id core-service assigned.
 */
public record FindingRef(RelativePath file, String symbol, AlgorithmFamily algorithmFamily, UsageContext usageContext,
        Optional<Integer> lineStart) {

    public FindingRef {
        Objects.requireNonNull(file, "file");
        Text.printable(symbol, 512, "symbol");
        Objects.requireNonNull(algorithmFamily, "algorithmFamily");
        Objects.requireNonNull(usageContext, "usageContext");
        Objects.requireNonNull(lineStart, "lineStart");
        lineStart.ifPresent(line -> {
            if (line < 1) {
                throw new IllegalArgumentException("lineStart must be at least 1");
            }
        });
    }

    /** The reference to a usage. */
    public static FindingRef of(CryptoUsage usage) {
        return new FindingRef(usage.evidence().file(), usage.symbol(), usage.algorithm().family(), usage.usageContext(),
                usage.evidence().lines().map(LineRange::start));
    }
}
