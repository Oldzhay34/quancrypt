package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.Optional;

/** A consent; version is the optimistic lock value (If-Match). */
public record ConsentView(String consentType, int privacyNoticeVersion, Instant grantedAt, Optional<Instant> revokedAt, int version, boolean created) {
}
