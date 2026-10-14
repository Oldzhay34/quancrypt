package com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem;

/** What a PEM file holds, from its header line. */
public enum PemRole {
    CERTIFICATE,
    PUBLIC_KEY,
    PRIVATE_KEY,
    OTHER
}
