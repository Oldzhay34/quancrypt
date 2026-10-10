package com.quancrypt.core.infrastructure.persistence.scan;

import com.quancrypt.core.domain.exception.ScanAlreadyRunningException;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.port.outbound.ScanWriter;
import java.time.Instant;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Writes scans; the partial unique index allows one running scan per project (no SERIALIZABLE needed). */
public final class JdbcScanWriter implements ScanWriter {

    static final String ONE_RUNNING_PER_PROJECT = "uq_scan_one_running_per_project";

    private final JdbcClient jdbc;

    public JdbcScanWriter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void insertRunning(Scan scan) {
        try {
            jdbc.sql("""
                    INSERT INTO scan (id, project_id, runtime_profile_sequence_no, status, started_at, completed_at)
                    VALUES (:id, :projectId, :sequenceNo, 'RUNNING', :startedAt, NULL)""")
                    .param("id", scan.id())
                    .param("projectId", scan.projectId())
                    .param("sequenceNo", scan.runtimeProfileSequenceNo().orElse(null))
                    .param("startedAt", Sql.ts(scan.startedAt()))
                    .update();
        } catch (DataIntegrityViolationException e) {
            if (SqlErrors.isUniqueViolation(e, ONE_RUNNING_PER_PROJECT)) {
                throw new ScanAlreadyRunningException();
            }
            throw e;
        }
    }

    @Override
    public boolean finishIfRunning(UUID scanId, ScanStatus outcome, Instant at) {
        if (outcome == ScanStatus.RUNNING) {
            throw new IllegalArgumentException("a scan finishes as COMPLETED or FAILED");
        }
        return jdbc.sql("UPDATE scan SET status = :status, completed_at = :at WHERE id = :id AND status = 'RUNNING'")
                .param("status", outcome.name()).param("at", Sql.ts(at)).param("id", scanId)
                .update() == 1;
    }
}
