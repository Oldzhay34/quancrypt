package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import java.util.Optional;

/** The key a TLS connection authenticates with, as far as the project's files tell; {@code certain} is false for a guess. */
public record TlsIdentity(Optional<AlgorithmFamily> family, Optional<Integer> keySizeBits, boolean certain) {

    public static final TlsIdentity UNKNOWN = new TlsIdentity(Optional.empty(), Optional.empty(), false);

    /** The confidence of a finding built on this identity: 0.8 when read from the bundle's own file, 0.5 as a guess, 0.4 without a key. */
    public double confidence() {
        return family.isEmpty() ? 0.4 : certain ? 0.8 : 0.5;
    }

    /** The algorithm of a TLS connection that authenticates with this key; {@code mode} is the protocol when known. */
    public CryptoAlgorithm algorithm(String rawName, String mode) {
        return new CryptoAlgorithm(family.orElse(AlgorithmFamily.UNKNOWN), rawName, Optional.ofNullable(mode), Optional.empty(), Optional.empty(),
                keySizeBits);
    }
}
