package com.quancrypt.core.infrastructure.persistence.audit;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.AuditLogReader;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Pages a project's audit entries, newest first (ix_audit_log_project_key_occurred_at). */
public final class JdbcAuditLogReader implements AuditLogReader {

    private final JdbcClient jdbc;

    public JdbcAuditLogReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public PageResult<AuditEntry> page(ProjectKey projectKey, int page, int size) {
        List<AuditEntry> items = jdbc.sql("""
                SELECT id, occurred_at, action_code, project_key, subject_id, caller_kind FROM audit_log
                WHERE project_key = :key ORDER BY occurred_at DESC, id DESC LIMIT :size OFFSET :offset""")
                .param("key", projectKey.value()).param("size", size).param("offset", Sql.offset(page, size))
                .query((rs, n) -> new AuditEntry(
                        Sql.uuid(rs, "id"),
                        Sql.instant(rs, "occurred_at"),
                        Sql.code(rs, "action_code", AuditAction.class),
                        Optional.of(new ProjectKey(rs.getString("project_key"))),
                        Sql.optUuid(rs, "subject_id"),
                        Sql.code(rs, "caller_kind", CallerKind.class)))
                .list();
        long total = jdbc.sql("SELECT count(*) FROM audit_log WHERE project_key = :key").param("key", projectKey.value())
                .query(Long.class).single();
        return new PageResult<>(items, page, size, total);
    }
}
