package com.quancrypt.analyzer.domain.model;

import java.util.Optional;

/** Algorithm family code list of crypto-domain, each with its quantum status (empty for UNKNOWN). */
public enum AlgorithmFamily {
    RSA(QuantumStatus.VULNERABLE),
    ECDSA(QuantumStatus.VULNERABLE),
    ECDH(QuantumStatus.VULNERABLE),
    EDDSA(QuantumStatus.VULNERABLE),
    DH(QuantumStatus.VULNERABLE),
    DSA(QuantumStatus.VULNERABLE),
    ML_KEM(QuantumStatus.RESISTANT),
    ML_DSA(QuantumStatus.RESISTANT),
    SLH_DSA(QuantumStatus.RESISTANT),
    AES(QuantumStatus.SYMMETRIC_OR_HASH),
    DES(QuantumStatus.SYMMETRIC_OR_HASH),
    TRIPLE_DES(QuantumStatus.SYMMETRIC_OR_HASH),
    CHACHA20(QuantumStatus.SYMMETRIC_OR_HASH),
    SHA1(QuantumStatus.SYMMETRIC_OR_HASH),
    SHA2(QuantumStatus.SYMMETRIC_OR_HASH),
    SHA3(QuantumStatus.SYMMETRIC_OR_HASH),
    MD5(QuantumStatus.SYMMETRIC_OR_HASH),
    HMAC(QuantumStatus.SYMMETRIC_OR_HASH),
    X25519(QuantumStatus.VULNERABLE),
    HYBRID_X25519_MLKEM768(QuantumStatus.RESISTANT),
    UNKNOWN(null);

    private final QuantumStatus quantumStatus;

    AlgorithmFamily(QuantumStatus quantumStatus) {
        this.quantumStatus = quantumStatus;
    }

    /** Empty for {@link #UNKNOWN}. */
    public Optional<QuantumStatus> quantumStatus() {
        return Optional.ofNullable(quantumStatus);
    }

    public boolean isQuantumVulnerable() {
        return quantumStatus == QuantumStatus.VULNERABLE;
    }
}
