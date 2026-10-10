package com.quancrypt.core.infrastructure.persistence.profile;

import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.RuntimeProfileWriter;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Appends a runtime profile; the caller holds the project row FOR NO KEY UPDATE, so sequence numbers do not race. */
public final class JdbcRuntimeProfileWriter implements RuntimeProfileWriter {

    private final JdbcClient jdbc;
    private final IdGenerator ids;

    public JdbcRuntimeProfileWriter(JdbcClient jdbc, IdGenerator ids) {
        this.jdbc = jdbc;
        this.ids = ids;
    }

    @Override
    public void insert(UUID projectId, RuntimeProfile profile) {
        jdbc.sql("""
                INSERT INTO project_runtime_profile (id, project_id, sequence_no, java_version, spring_boot_version, recorded_at)
                VALUES (:id, :projectId, :sequenceNo, :javaVersion, :springBootVersion, :recordedAt)""")
                .param("id", ids.next())
                .param("projectId", projectId)
                .param("sequenceNo", profile.sequenceNo())
                .param("javaVersion", profile.javaVersion())
                .param("springBootVersion", profile.springBootVersion().orElse(null))
                .param("recordedAt", Sql.ts(profile.recordedAt()))
                .update();
    }
}
