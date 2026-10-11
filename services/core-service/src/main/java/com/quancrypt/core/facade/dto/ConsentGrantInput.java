package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/** Body of GrantConsent (schema ConsentGrant). */
public record ConsentGrantInput(@NotNull String consentType, @NotNull @Min(1) Integer privacyNoticeVersion) {
}
