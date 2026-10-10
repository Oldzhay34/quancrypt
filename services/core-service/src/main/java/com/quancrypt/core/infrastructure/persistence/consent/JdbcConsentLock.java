package com.quancrypt.core.infrastructure.persistence.consent;

import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.port.outbound.ConsentLock;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Row locks on consents; only the consent row is locked, not the privacy notice it joins. */
public final class JdbcConsentLock implements ConsentLock {

    private final JdbcClient jdbc;

    public JdbcConsentLock(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Consent> share(UUID projectId, ConsentType type) {
        return jdbc.sql(ConsentRows.SELECT + " WHERE c.project_id = :projectId AND c.consent_type = :type FOR SHARE OF c")
                .param("projectId", projectId).param("type", type.name()).query(ConsentRows::map).optional();
    }

    @Override
    public List<Consent> updateAll(UUID projectId) {
        return jdbc.sql(ConsentRows.SELECT + " WHERE c.project_id = :projectId ORDER BY c.id FOR UPDATE OF c")
                .param("projectId", projectId).query(ConsentRows::map).list();
    }
}
