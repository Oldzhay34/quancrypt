package com.quancrypt.core.port.inbound;

import java.util.Optional;
import java.util.UUID;

/** Grants a consent, or grants it again after a revoke (expectedVersion required then). */
public record GrantConsentCommand(UUID projectId, String consentType, int privacyNoticeVersion, Optional<Integer> expectedVersion, Optional<Idempotency> idempotency, String caller) {
}
