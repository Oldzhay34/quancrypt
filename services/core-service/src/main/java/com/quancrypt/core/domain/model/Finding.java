package com.quancrypt.core.domain.model;

import java.util.Optional;
import java.util.UUID;

/** A crypto finding; the scan is reached through its source file, evidence is path and line range only (D-126, D-131). */
public record Finding(
        UUID id,
        UUID sourceFileId,
        String symbol,
        AlgorithmFamily algorithm,
        UsageContext usage,
        Priority priority,
        Optional<Integer> keySizeBits,
        Optional<Integer> lineStart,
        Optional<Integer> lineEnd,
        double confidence,
        ClassifiedBy classifiedBy) {

    public static final int MAX_SYMBOL = 512;

    public Finding {
        if (symbol == null || symbol.isBlank() || symbol.length() > MAX_SYMBOL) {
            throw new IllegalArgumentException("symbol must be 1.." + MAX_SYMBOL + " characters");
        }
        if (confidence < 0.0 || confidence > 1.0) {
            throw new IllegalArgumentException("confidence must be between 0 and 1");
        }
        keySizeBits.ifPresent(bits -> {
            if (bits < 1) {
                throw new IllegalArgumentException("key size must be positive");
            }
        });
        if (lineStart.isPresent() != lineEnd.isPresent()) {
            throw new IllegalArgumentException("line start and end are given together or not at all");
        }
        if (lineStart.isPresent() && (lineStart.get() < 1 || lineEnd.get() < lineStart.get())) {
            throw new IllegalArgumentException("line range must start at 1 or later and not end before it starts");
        }
    }

    public CryptoUsage cryptoUsage(LocationKind locationKind) {
        return new CryptoUsage(algorithm, usage, keySizeBits, locationKind);
    }
}
