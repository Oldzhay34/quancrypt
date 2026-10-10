package com.quancrypt.core.infrastructure.persistence.consent;

import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.port.outbound.ConsentReader;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads consents without locks. */
public final class JdbcConsentReader implements ConsentReader {

    private final JdbcClient jdbc;

    public JdbcConsentReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Consent> find(UUID projectId, ConsentType type) {
        return jdbc.sql(ConsentRows.SELECT + " WHERE c.project_id = :projectId AND c.consent_type = :type")
                .param("projectId", projectId).param("type", type.name()).query(ConsentRows::map).optional();
    }

    @Override
    public List<Consent> list(UUID projectId) {
        return jdbc.sql(ConsentRows.SELECT + " JOIN consent_type t ON t.code = c.consent_type WHERE c.project_id = :projectId ORDER BY t.sort_order")
                .param("projectId", projectId).query(ConsentRows::map).list();
    }
}
