package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.NotNull;

/** Body of CompleteScan (schema ScanCompletion). */
public record ScanCompletionInput(@NotNull String outcome) {
}
