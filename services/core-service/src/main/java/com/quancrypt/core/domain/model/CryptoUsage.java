package com.quancrypt.core.domain.model;

import java.util.Optional;

/** The facts of one crypto usage that decide its migration priority (crypto-domain priority table). */
public record CryptoUsage(
        AlgorithmFamily algorithm,
        UsageContext usage,
        Optional<Integer> keySizeBits,
        LocationKind locationKind) {
}
