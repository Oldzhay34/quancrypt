package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import java.util.List;

/** Which dependencies are crypto libraries worth a fact in the CBOM. */
final class CryptoLibraries {

    private static final List<String> GROUPS = List.of("org.bouncycastle", "io.jsonwebtoken", "com.nimbusds", "com.auth0", "org.eclipse.paho",
            "org.conscrypt", "com.google.crypto.tink");

    private CryptoLibraries() {
    }

    static boolean isCrypto(String group, String artifact) {
        if (group.equals("com.auth0")) {
            return artifact.contains("jwt");
        }
        return GROUPS.contains(group) || (group.equals("org.springframework.security") && artifact.contains("oauth2-jose"));
    }
}
