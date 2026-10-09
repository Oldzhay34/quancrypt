package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Revokes a consent. */
public record RevokeConsentCommand(UUID projectId, String consentType, int expectedVersion, String caller) {
}
