package com.quancrypt.core.infrastructure.persistence.scan;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.ScanReader;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads scans; a project's scans are paged newest first. */
public final class JdbcScanReader implements ScanReader {

    private final JdbcClient jdbc;

    public JdbcScanReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Scan> find(UUID scanId) {
        return jdbc.sql("SELECT " + ScanRows.COLUMNS + " FROM scan WHERE id = :id").param("id", scanId).query(ScanRows::map).optional();
    }

    @Override
    public Optional<UUID> projectIdOf(UUID scanId) {
        return jdbc.sql("SELECT project_id FROM scan WHERE id = :id").param("id", scanId).query(UUID.class).optional();
    }

    @Override
    public PageResult<Scan> pageByProject(UUID projectId, int page, int size) {
        List<Scan> items = jdbc.sql("SELECT " + ScanRows.COLUMNS
                + " FROM scan WHERE project_id = :projectId ORDER BY started_at DESC, id DESC LIMIT :size OFFSET :offset")
                .param("projectId", projectId).param("size", size).param("offset", Sql.offset(page, size))
                .query(ScanRows::map).list();
        long total = jdbc.sql("SELECT count(*) FROM scan WHERE project_id = :projectId")
                .param("projectId", projectId).query(Long.class).single();
        return new PageResult<>(items, page, size, total);
    }
}
