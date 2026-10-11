package com.quancrypt.analyzer.domain.model;

import java.util.Objects;
import java.util.Optional;

/**
 * The algorithm of a crypto usage: its family code and the raw name, mode, padding and hash as written in the code
 * (D-174), and the key size when it is known.
 */
public record CryptoAlgorithm(AlgorithmFamily family, String rawName, Optional<String> mode, Optional<String> padding,
        Optional<String> hash, Optional<Integer> keySizeBits) {

    public CryptoAlgorithm {
        Objects.requireNonNull(family, "family");
        Text.printable(rawName, 256, "rawName");
        Text.optionalMatching(mode, Text.TOKEN, "mode");
        Text.optionalMatching(padding, Text.TOKEN, "padding");
        Text.optionalMatching(hash, Text.TOKEN, "hash");
        Objects.requireNonNull(keySizeBits, "keySizeBits");
        keySizeBits.ifPresent(bits -> {
            if (bits < 1) {
                throw new IllegalArgumentException("keySizeBits must be positive");
            }
        });
    }
}
