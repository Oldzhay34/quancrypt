package com.quancrypt.core.infrastructure.persistence.finding;

import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.port.outbound.SourceFileWriter;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Writes source files as one batch; the scan's (scan_id, path) is unique. */
public final class JdbcSourceFileWriter implements SourceFileWriter {

    private final JdbcClient jdbc;
    private final NamedParameterJdbcOperations batch;

    public JdbcSourceFileWriter(JdbcClient jdbc, NamedParameterJdbcOperations batch) {
        this.jdbc = jdbc;
        this.batch = batch;
    }

    @Override
    public void insertAll(List<SourceFile> files) {
        if (files.isEmpty()) {
            return;
        }
        SqlParameterSource[] rows = files.stream()
                .map(f -> new MapSqlParameterSource()
                        .addValue("id", f.id()).addValue("scanId", f.scanId()).addValue("path", f.path())
                        .addValue("kind", f.locationKind().name()))
                .toArray(SqlParameterSource[]::new);
        batch.batchUpdate("INSERT INTO source_file (id, scan_id, path, location_kind) VALUES (:id, :scanId, :path, :kind)", rows);
    }

    @Override
    public int deleteUnreferenced(UUID scanId) {
        return jdbc.sql("""
                DELETE FROM source_file sf
                WHERE sf.scan_id = :scanId
                  AND NOT EXISTS (SELECT 1 FROM finding f WHERE f.source_file_id = sf.id)
                  AND NOT EXISTS (SELECT 1 FROM link_call_site cs WHERE cs.source_file_id = sf.id)""")
                .param("scanId", scanId).update();
    }
}
