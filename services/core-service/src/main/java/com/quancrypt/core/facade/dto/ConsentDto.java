package com.quancrypt.core.facade.dto;

import java.time.Instant;

/** Consent (schema Consent); revokedAt is null while the consent is active. */
public record ConsentDto(String consentType, int privacyNoticeVersion, Instant grantedAt, Instant revokedAt, int version) {
}
