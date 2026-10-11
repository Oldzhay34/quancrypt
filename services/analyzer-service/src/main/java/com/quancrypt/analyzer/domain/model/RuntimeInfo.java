package com.quancrypt.analyzer.domain.model;

import java.util.Optional;

/** Java and Spring Boot versions found in the build files; a version that cannot be found is empty. */
public record RuntimeInfo(Optional<String> javaVersion, Optional<String> springBootVersion) {

    public static final RuntimeInfo UNKNOWN = new RuntimeInfo(Optional.empty(), Optional.empty());

    public RuntimeInfo {
        Text.optionalMatching(javaVersion, Text.VERSION, "javaVersion");
        Text.optionalMatching(springBootVersion, Text.VERSION, "springBootVersion");
    }
}
