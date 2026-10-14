package com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.Optional;

/**
 * What is known about a PEM file. For certificates and public keys it comes from the key itself; for private keys only
 * from the header and the matching public file (private keys are never parsed, D-19, D-185).
 */
public record PemFacts(RelativePath file, PemRole role, String label, Optional<AlgorithmFamily> family, Optional<Integer> keySizeBits,
        Optional<CryptoAlgorithm> signature) {

    public PemFacts withKey(Optional<AlgorithmFamily> newFamily, Optional<Integer> newKeySize) {
        return new PemFacts(file, role, label, newFamily, newKeySize, signature);
    }
}
