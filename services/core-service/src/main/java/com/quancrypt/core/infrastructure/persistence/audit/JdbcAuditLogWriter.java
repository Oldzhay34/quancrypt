package com.quancrypt.core.infrastructure.persistence.audit;

import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Appends audit entries: time, action code, project key, subject id and caller kind; no personal data (D-125). */
public final class JdbcAuditLogWriter implements AuditLogWriter {

    private final JdbcClient jdbc;

    public JdbcAuditLogWriter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void append(AuditEntry entry) {
        jdbc.sql("""
                INSERT INTO audit_log (id, occurred_at, action_code, project_key, subject_id, caller_kind)
                VALUES (:id, :at, :action, :projectKey, :subjectId, :caller)""")
                .param("id", entry.id())
                .param("at", Sql.ts(entry.occurredAt()))
                .param("action", entry.action().name())
                .param("projectKey", entry.projectKey().map(ProjectKey::value).orElse(null))
                .param("subjectId", entry.subjectId().orElse(null))
                .param("caller", entry.caller().name())
                .update();
    }
}
