package com.quancrypt.core.infrastructure.persistence.project;

import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.ProjectWriter;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Writes projects; the unique project_key settles concurrent registrations (no lock needed). */
public final class JdbcProjectWriter implements ProjectWriter {

    private final JdbcClient jdbc;

    public JdbcProjectWriter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public boolean insertIfAbsent(Project project) {
        return jdbc.sql("""
                INSERT INTO project (id, project_key, display_name, created_at)
                VALUES (:id, :key, :name, :createdAt)
                ON CONFLICT (project_key) DO NOTHING""")
                .param("id", project.id())
                .param("key", project.key().value())
                .param("name", project.displayName())
                .param("createdAt", Sql.ts(project.createdAt()))
                .update() == 1;
    }

    @Override
    public void delete(UUID projectId) {
        jdbc.sql("DELETE FROM project WHERE id = :id").param("id", projectId).update();
    }
}
