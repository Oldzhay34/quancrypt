package com.quancrypt.core.infrastructure.persistence.project;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.ProjectReader;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads projects; pages are newest first. */
public final class JdbcProjectReader implements ProjectReader {

    private final JdbcClient jdbc;

    public JdbcProjectReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Project> findById(UUID projectId) {
        return jdbc.sql("SELECT " + ProjectRows.COLUMNS + " FROM project WHERE id = :id")
                .param("id", projectId).query(ProjectRows::map).optional();
    }

    @Override
    public Optional<Project> findByKey(ProjectKey key) {
        return jdbc.sql("SELECT " + ProjectRows.COLUMNS + " FROM project WHERE project_key = :key")
                .param("key", key.value()).query(ProjectRows::map).optional();
    }

    @Override
    public PageResult<Project> page(int page, int size) {
        List<Project> items = jdbc.sql("SELECT " + ProjectRows.COLUMNS + " FROM project ORDER BY created_at DESC, id DESC LIMIT :size OFFSET :offset")
                .param("size", size).param("offset", Sql.offset(page, size)).query(ProjectRows::map).list();
        long total = jdbc.sql("SELECT count(*) FROM project").query(Long.class).single();
        return new PageResult<>(items, page, size, total);
    }
}
