package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/** Body of RecordRuntimeProfile (schema RuntimeProfileInput). */
public record RuntimeProfileInput(@NotNull @Pattern(regexp = "^[0-9A-Za-z._+-]{1,32}$") String javaVersion, @Pattern(regexp = "^[0-9A-Za-z._+-]{1,32}$") String springBootVersion) {
}
