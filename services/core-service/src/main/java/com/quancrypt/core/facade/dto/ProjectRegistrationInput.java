package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** Body of RegisterProject (schema ProjectRegistration). */
public record ProjectRegistrationInput(@NotBlank @Size(max = 2048) String identity, @NotBlank @Size(max = 200) String displayName) {
}
