package com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;

/**
 * A Spring Boot SSL bundle (spring.ssl.bundle.pem.NAME or .jks.NAME): the keystore references are the bundle's own
 * identity, the truststore references only the certificates it trusts.
 */
public record SslBundle(String name, String type, RelativePath file, int line, List<String> keystoreReferences,
        List<String> truststoreReferences) {

    public SslBundle {
        keystoreReferences = List.copyOf(keystoreReferences);
        truststoreReferences = List.copyOf(truststoreReferences);
    }

    public boolean hasIdentity() {
        return !keystoreReferences.isEmpty();
    }

    public boolean isJks() {
        return type.equals("jks");
    }
}
