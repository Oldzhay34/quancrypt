package com.quancrypt.core.infrastructure.persistence.scan;

import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.ScanArtifactWriter;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Stores the scan's CBOM file; a later PUT replaces it (one file per scan). */
public final class JdbcScanArtifactWriter implements ScanArtifactWriter {

    private final JdbcClient jdbc;
    private final IdGenerator ids;

    public JdbcScanArtifactWriter(JdbcClient jdbc, IdGenerator ids) {
        this.jdbc = jdbc;
        this.ids = ids;
    }

    @Override
    public void save(ScanArtifact artifact) {
        jdbc.sql("""
                INSERT INTO scan_artifact (id, scan_id, content, content_type, sha256, created_at)
                VALUES (:id, :scanId, :content, :contentType, :sha256, :createdAt)
                ON CONFLICT (scan_id) DO UPDATE
                SET content = EXCLUDED.content, content_type = EXCLUDED.content_type, sha256 = EXCLUDED.sha256,
                    created_at = EXCLUDED.created_at""")
                .param("id", ids.next())
                .param("scanId", artifact.scanId())
                .param("content", artifact.content())
                .param("contentType", artifact.contentType())
                .param("sha256", artifact.sha256())
                .param("createdAt", Sql.ts(artifact.createdAt()))
                .update();
    }
}
