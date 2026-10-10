package com.quancrypt.core.infrastructure.persistence.project;

import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.outbound.ProjectLock;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Row locks on a project, the first lock of every writer (D-143). */
public final class JdbcProjectLock implements ProjectLock {

    private final JdbcClient jdbc;

    public JdbcProjectLock(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Project> keyShare(UUID projectId) {
        return lock(projectId, "FOR KEY SHARE");
    }

    @Override
    public Optional<Project> noKeyUpdate(UUID projectId) {
        return lock(projectId, "FOR NO KEY UPDATE");
    }

    @Override
    public Optional<Project> update(UUID projectId) {
        return lock(projectId, "FOR UPDATE");
    }

    private Optional<Project> lock(UUID projectId, String mode) {
        return jdbc.sql("SELECT " + ProjectRows.COLUMNS + " FROM project WHERE id = :id " + mode)
                .param("id", projectId).query(ProjectRows::map).optional();
    }
}
