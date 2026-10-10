package com.quancrypt.core.infrastructure.persistence.project;

import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.persistence.Sql;
import java.sql.ResultSet;
import java.sql.SQLException;

/** Column list and row mapping of the project table. */
final class ProjectRows {

    static final String COLUMNS = "id, project_key, display_name, created_at";

    private ProjectRows() {
    }

    static Project map(ResultSet rs, int rowNum) throws SQLException {
        return new Project(Sql.uuid(rs, "id"), new ProjectKey(rs.getString("project_key")), rs.getString("display_name"),
                Sql.instant(rs, "created_at"));
    }
}
