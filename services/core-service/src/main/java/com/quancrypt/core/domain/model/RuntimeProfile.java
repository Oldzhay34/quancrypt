package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Optional;

/** One entry of a project's runtime history: Java and optional Spring Boot version (SCD2-like). */
public record RuntimeProfile(int sequenceNo, String javaVersion, Optional<String> springBootVersion, Instant recordedAt) {

    public RuntimeProfile {
        if (sequenceNo < 1) {
            throw new IllegalArgumentException("sequence number must be positive");
        }
        requireVersion(javaVersion);
        springBootVersion.ifPresent(RuntimeProfile::requireVersion);
    }

    private static void requireVersion(String version) {
        if (version == null || !version.matches("^[0-9A-Za-z._+-]{1,32}$")) {
            throw new IllegalArgumentException("version must match [0-9A-Za-z._+-]{1,32}");
        }
    }

    public Optional<JavaVersion> java() {
        return JavaVersion.parse(javaVersion);
    }

    /** Same versions as another profile, ignoring sequence number and time. */
    public boolean sameVersionsAs(String otherJava, Optional<String> otherSpringBoot) {
        return javaVersion.equals(otherJava) && springBootVersion.equals(otherSpringBoot);
    }
}
