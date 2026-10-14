package com.quancrypt.analyzer.domain.model;

/** What a row of the canonical dictionary maps (the first CSV column). */
public enum CanonicalKind {
    /** A whole JCA transformation such as RSA/ECB/PKCS1Padding. */
    TRANSFORMATION,
    /** The algorithm part of a transformation or a key algorithm name (AES, RSA, DESede). */
    ALGORITHM,
    /** The mode part of a transformation (CBC, GCM). */
    MODE,
    /** The padding part of a transformation (PKCS1Padding, OAEPWithSHA-256AndMGF1Padding). */
    PADDING,
    /** A JCA signature algorithm (SHA256withRSA). */
    SIGNATURE,
    /** A JWS algorithm (RS256). */
    JWT_ALG,
    /** An object identifier. */
    OID,
    /** A JDK public key algorithm name (RSA, EC, Ed25519). */
    PUBKEY_ALG,
    /** A message digest name (SHA-256, SHA1). */
    HASH,
    /** A key size notation (2K, 2048). */
    KEY_SIZE,
    /** A TLS protocol name (TLSv1.2). */
    TLS_PROTOCOL
}
