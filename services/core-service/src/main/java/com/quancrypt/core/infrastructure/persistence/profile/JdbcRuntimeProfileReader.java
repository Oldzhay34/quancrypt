package com.quancrypt.core.infrastructure.persistence.profile;

import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads the runtime profile history; the current profile comes from v_project_current_runtime. */
public final class JdbcRuntimeProfileReader implements RuntimeProfileReader {

    private final JdbcClient jdbc;

    public JdbcRuntimeProfileReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<RuntimeProfile> current(UUID projectId) {
        return jdbc.sql("""
                SELECT sequence_no, java_version, spring_boot_version, recorded_at
                FROM v_project_current_runtime WHERE project_id = :projectId""")
                .param("projectId", projectId).query(JdbcRuntimeProfileReader::map).optional();
    }

    @Override
    public Optional<RuntimeProfile> bySequence(UUID projectId, int sequenceNo) {
        return jdbc.sql("""
                SELECT sequence_no, java_version, spring_boot_version, recorded_at
                FROM project_runtime_profile WHERE project_id = :projectId AND sequence_no = :sequenceNo""")
                .param("projectId", projectId).param("sequenceNo", sequenceNo).query(JdbcRuntimeProfileReader::map).optional();
    }

    private static RuntimeProfile map(ResultSet rs, int rowNum) throws SQLException {
        return new RuntimeProfile(rs.getInt("sequence_no"), rs.getString("java_version"), Sql.optString(rs, "spring_boot_version"),
                Sql.instant(rs, "recorded_at"));
    }
}
