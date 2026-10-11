package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** Clarification answer (schema ClarificationAnswer; also the response item). */
public record ClarificationAnswerDto(@NotNull String questionCode, @Size(max = 32) String optionCode, @Size(max = 500) String freeText) {
}
