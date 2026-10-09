package com.quancrypt.core.domain.model;

/** Kind of the source a finding was found in (crypto-domain). */
public enum LocationKind {
    CODE,
    CONFIG,
    CERTIFICATE_FILE,
    KEYSTORE_FILE,
    BUILD_FILE,
    TEST_CODE;
}
