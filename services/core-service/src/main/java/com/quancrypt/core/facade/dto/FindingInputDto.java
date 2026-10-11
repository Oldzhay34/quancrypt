package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** One finding of a batch (schema FindingInput). */
public record FindingInputDto(@NotBlank @Size(max = 1024) String path, @NotBlank @Size(max = 512) String symbol, @NotNull String algorithmFamily, @NotNull String usageContext, @NotNull String locationKind, @NotNull String priority, @Min(1) Integer keySizeBits, @Min(1) Integer lineStart, @Min(1) Integer lineEnd, @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double confidence, @NotNull String classifiedBy) {
}
