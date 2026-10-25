import type { AlgorithmFamily, Finding } from '@/shared/api/types';

/**
 * The quantum status of an algorithm family, as in crypto-domain: VULNERABLE (RSA, ECDSA, ECDH, EdDSA, DH, DSA, X25519 alone),
 * RESISTANT (ML-KEM, ML-DSA, SLH-DSA, the hybrid group), SYMMETRIC_OR_HASH (symmetric ciphers and hashes), UNKNOWN. MIXED is only
 * for a connection that uses both vulnerable and resistant algorithms.
 */
export type QuantumStatus = 'VULNERABLE' | 'RESISTANT' | 'SYMMETRIC_OR_HASH' | 'MIXED' | 'UNKNOWN';

const VULNERABLE: ReadonlySet<AlgorithmFamily> = new Set([
    'RSA',
    'ECDSA',
    'ECDH',
    'EDDSA',
    'DH',
    'DSA',
    'X25519',
]);
const RESISTANT: ReadonlySet<AlgorithmFamily> = new Set([
    'ML_KEM',
    'ML_DSA',
    'SLH_DSA',
    'HYBRID_X25519_MLKEM768',
]);
const SYMMETRIC_OR_HASH: ReadonlySet<AlgorithmFamily> = new Set([
    'AES',
    'DES',
    'TRIPLE_DES',
    'CHACHA20',
    'SHA1',
    'SHA2',
    'SHA3',
    'MD5',
    'HMAC',
]);

export function familyStatus(family: AlgorithmFamily): Exclude<QuantumStatus, 'MIXED'> {
    if (VULNERABLE.has(family)) return 'VULNERABLE';
    if (RESISTANT.has(family)) return 'RESISTANT';
    if (SYMMETRIC_OR_HASH.has(family)) return 'SYMMETRIC_OR_HASH';
    return 'UNKNOWN';
}

/**
 * The status of a connection, derived from the findings linked to it (the service does not record one per connection): any
 * vulnerable algorithm makes it VULNERABLE, unless a resistant one is also present (MIXED); only resistant: RESISTANT; only
 * symmetric or hash: SYMMETRIC_OR_HASH; no finding or only unknown algorithms: UNKNOWN.
 */
export function edgeStatus(findings: readonly Pick<Finding, 'algorithmFamily'>[]): QuantumStatus {
    const found = new Set(findings.map((finding) => familyStatus(finding.algorithmFamily)));
    if (found.has('VULNERABLE') && found.has('RESISTANT')) return 'MIXED';
    if (found.has('VULNERABLE')) return 'VULNERABLE';
    if (found.has('RESISTANT')) return 'RESISTANT';
    if (found.has('SYMMETRIC_OR_HASH')) return 'SYMMETRIC_OR_HASH';
    return 'UNKNOWN';
}
