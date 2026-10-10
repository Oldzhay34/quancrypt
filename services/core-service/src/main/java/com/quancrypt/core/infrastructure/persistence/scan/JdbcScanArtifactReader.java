package com.quancrypt.core.infrastructure.persistence.scan;

import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.ScanArtifactReader;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads the CBOM file of a scan from one row (opaque bytea). */
public final class JdbcScanArtifactReader implements ScanArtifactReader {

    private final JdbcClient jdbc;

    public JdbcScanArtifactReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<ScanArtifact> find(UUID scanId) {
        return jdbc.sql("SELECT scan_id, content_type, content, sha256, created_at FROM scan_artifact WHERE scan_id = :scanId")
                .param("scanId", scanId)
                .query((rs, n) -> new ScanArtifact(Sql.uuid(rs, "scan_id"), rs.getString("content_type"), rs.getBytes("content"),
                        rs.getString("sha256"), Sql.instant(rs, "created_at")))
                .optional();
    }
}
