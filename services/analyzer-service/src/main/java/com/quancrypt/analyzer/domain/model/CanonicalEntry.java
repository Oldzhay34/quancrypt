package com.quancrypt.analyzer.domain.model;

import java.util.Objects;
import java.util.Optional;

/**
 * One row of the canonical dictionary: a raw spelling and the crypto-domain codes it stands for. Empty parts say nothing
 * (a MODE row only sets the mode). Values are the dictionary's canonical vocabulary (D-190i).
 */
public record CanonicalEntry(CanonicalKind kind, String raw, Optional<AlgorithmFamily> family, Optional<String> mode,
        Optional<String> padding, Optional<String> hash, Optional<UsageContext> usage, Optional<Integer> keySizeBits) {

    public CanonicalEntry {
        Objects.requireNonNull(kind, "kind");
        Text.printable(raw, 256, "raw");
        Objects.requireNonNull(family, "family");
        Text.optionalMatching(mode, Text.TOKEN, "mode");
        Text.optionalMatching(padding, Text.TOKEN, "padding");
        Text.optionalMatching(hash, Text.TOKEN, "hash");
        Objects.requireNonNull(usage, "usage");
        Objects.requireNonNull(keySizeBits, "keySizeBits");
        keySizeBits.ifPresent(bits -> {
            if (bits < 1) {
                throw new IllegalArgumentException("keySizeBits must be positive");
            }
        });
    }
}
