package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** Call site of a link (schema CallSiteInput). */
public record CallSiteInputDto(@NotBlank @Size(max = 1024) String path, @NotNull @Min(1) Integer lineStart, @NotNull @Min(1) Integer lineEnd, @NotNull String locationKind) {
}
