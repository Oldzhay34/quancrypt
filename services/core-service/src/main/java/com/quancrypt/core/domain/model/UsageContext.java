package com.quancrypt.core.domain.model;

/** Usage context code list (crypto-domain). */
public enum UsageContext {
    TLS_KEY_EXCHANGE,
    TLS_SERVER_AUTH,
    MTLS_CLIENT_AUTH,
    CERTIFICATE,
    ENCRYPTION,
    KEY_WRAP,
    SIGNATURE,
    TOKEN_SIGNATURE,
    KEY_AGREEMENT,
    HASH,
    SYMMETRIC_ENCRYPTION,
    KEYSTORE,
    UNKNOWN;
}
