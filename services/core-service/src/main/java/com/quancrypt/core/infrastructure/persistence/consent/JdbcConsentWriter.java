package com.quancrypt.core.infrastructure.persistence.consent;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.DuplicateConsentException;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.port.outbound.ConsentWriter;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Writes consents: the unique (project, type) settles concurrent first grants, the version column later changes. */
public final class JdbcConsentWriter implements ConsentWriter {

    static final String UNIQUE_PROJECT_TYPE = "uq_consent_project_type";

    private final JdbcClient jdbc;

    public JdbcConsentWriter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void insert(Consent consent) {
        try {
            jdbc.sql("""
                    INSERT INTO consent (id, project_id, consent_type, privacy_notice_id, granted_at, revoked_at, version)
                    VALUES (:id, :projectId, :type, :noticeId, :grantedAt, :revokedAt, :version)""")
                    .param("id", consent.id())
                    .param("projectId", consent.projectId())
                    .param("type", consent.type().name())
                    .param("noticeId", consent.privacyNoticeId())
                    .param("grantedAt", Sql.ts(consent.grantedAt()))
                    .param("revokedAt", Sql.ts(consent.revokedAt()))
                    .param("version", consent.version())
                    .update();
        } catch (DataIntegrityViolationException e) {
            if (SqlErrors.isUniqueViolation(e, UNIQUE_PROJECT_TYPE)) {
                throw new DuplicateConsentException();
            }
            throw e;
        }
    }

    @Override
    public void update(Consent updated, int expectedVersion) {
        int rows = jdbc.sql("""
                UPDATE consent
                SET privacy_notice_id = :noticeId, granted_at = :grantedAt, revoked_at = :revokedAt, version = :newVersion
                WHERE id = :id AND version = :expectedVersion""")
                .param("noticeId", updated.privacyNoticeId())
                .param("grantedAt", Sql.ts(updated.grantedAt()))
                .param("revokedAt", Sql.ts(updated.revokedAt()))
                .param("newVersion", updated.version())
                .param("id", updated.id())
                .param("expectedVersion", expectedVersion)
                .update();
        if (rows == 0) {
            throw new ConcurrentModificationException("consent");
        }
    }
}
