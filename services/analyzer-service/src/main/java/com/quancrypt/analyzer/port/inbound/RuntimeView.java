package com.quancrypt.analyzer.port.inbound;

import java.util.Optional;

/** Detected Java and Spring Boot versions. */
public record RuntimeView(Optional<String> javaVersion, Optional<String> springBootVersion) {
}
