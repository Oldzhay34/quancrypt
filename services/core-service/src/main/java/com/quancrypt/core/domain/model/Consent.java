package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** A project's consent of one type; valid while it is not revoked; optimistic version (D-21, D-135). */
public record Consent(
        UUID id,
        UUID projectId,
        ConsentType type,
        UUID privacyNoticeId,
        int privacyNoticeVersion,
        Instant grantedAt,
        Optional<Instant> revokedAt,
        int version) {

    public static Consent firstGrant(UUID id, UUID projectId, ConsentType type, PrivacyNotice notice, Instant at) {
        return new Consent(id, projectId, type, notice.id(), notice.version(), at, Optional.empty(), 0);
    }

    public boolean isActive() {
        return revokedAt.isEmpty();
    }

    public Consent revoke(Instant at) {
        if (!isActive()) {
            throw new IllegalStateException("consent is already revoked");
        }
        return new Consent(id, projectId, type, privacyNoticeId, privacyNoticeVersion, grantedAt, Optional.of(at), version + 1);
    }

    public Consent regrant(PrivacyNotice notice, Instant at) {
        if (isActive()) {
            throw new IllegalStateException("consent is already active");
        }
        return new Consent(id, projectId, type, notice.id(), notice.version(), at, Optional.empty(), version + 1);
    }
}
