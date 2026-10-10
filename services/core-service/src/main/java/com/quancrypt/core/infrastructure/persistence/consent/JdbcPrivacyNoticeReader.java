package com.quancrypt.core.infrastructure.persistence.consent;

import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.PrivacyNoticeReader;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads the privacy notice with the highest version (seeded by migration, D-135). */
public final class JdbcPrivacyNoticeReader implements PrivacyNoticeReader {

    private final JdbcClient jdbc;

    public JdbcPrivacyNoticeReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<PrivacyNotice> latest() {
        return jdbc.sql("SELECT id, version, text_tr, text_en, published_at FROM privacy_notice ORDER BY version DESC LIMIT 1")
                .query((rs, n) -> new PrivacyNotice(Sql.uuid(rs, "id"), rs.getInt("version"), rs.getString("text_tr"),
                        rs.getString("text_en"), Sql.instant(rs, "published_at")))
                .optional();
    }
}
