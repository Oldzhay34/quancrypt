package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** Node of a topology (schema NodeInput). */
public record NodeInputDto(@NotBlank @Size(max = 200) String name, @NotNull String nodeKind) {
}
