package com.quancrypt.core.facade.dto;

import java.time.Instant;

/** Runtime profile (schema RuntimeProfile); springBootVersion may be null. */
public record RuntimeProfileDto(int sequenceNo, String javaVersion, String springBootVersion, Instant recordedAt) {
}
