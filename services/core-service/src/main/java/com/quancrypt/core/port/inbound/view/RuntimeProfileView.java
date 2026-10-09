package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.Optional;

/** One runtime profile entry. */
public record RuntimeProfileView(int sequenceNo, String javaVersion, Optional<String> springBootVersion, Instant recordedAt, boolean created) {
}
