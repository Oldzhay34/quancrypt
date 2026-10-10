package com.quancrypt.core.infrastructure.persistence.consent;

import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.infrastructure.persistence.Sql;
import java.sql.ResultSet;
import java.sql.SQLException;

/** Select list and row mapping of a consent joined with the version of its privacy notice. */
final class ConsentRows {

    static final String SELECT = """
            SELECT c.id, c.project_id, c.consent_type, c.privacy_notice_id, n.version AS notice_version,
                   c.granted_at, c.revoked_at, c.version
            FROM consent c JOIN privacy_notice n ON n.id = c.privacy_notice_id""";

    private ConsentRows() {
    }

    static Consent map(ResultSet rs, int rowNum) throws SQLException {
        return new Consent(
                Sql.uuid(rs, "id"),
                Sql.uuid(rs, "project_id"),
                Sql.code(rs, "consent_type", ConsentType.class),
                Sql.uuid(rs, "privacy_notice_id"),
                rs.getInt("notice_version"),
                Sql.instant(rs, "granted_at"),
                Sql.optInstant(rs, "revoked_at"),
                rs.getInt("version"));
    }
}
