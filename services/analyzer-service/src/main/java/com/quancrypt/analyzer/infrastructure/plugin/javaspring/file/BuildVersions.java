package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import java.util.Optional;
import java.util.regex.Pattern;

/** The Java and Spring Boot versions found in one build file, validated against the contract's version pattern. */
record BuildVersions(Optional<String> java, Optional<String> boot) {

    private static final Pattern VERSION = Pattern.compile("[0-9A-Za-z._+-]{1,32}");

    static BuildVersions none() {
        return new BuildVersions(Optional.empty(), Optional.empty());
    }

    /** The version when it fits the pattern, with a leading "1." (Java 1.8) dropped when {@code java} is true. */
    static Optional<String> valid(String version, boolean java) {
        if (version == null || !VERSION.matcher(version).matches()) {
            return Optional.empty();
        }
        return Optional.of(java && version.startsWith("1.") ? version.substring(2) : version);
    }
}
