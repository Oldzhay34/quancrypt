package com.quancrypt.analyzer.domain.model;

/** Kind of source a finding or an evidence comes from (crypto-domain). */
public enum LocationKind {
    CODE, CONFIG, CERTIFICATE_FILE, KEYSTORE_FILE, BUILD_FILE, TEST_CODE
}
