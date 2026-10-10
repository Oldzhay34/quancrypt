package com.quancrypt.core.infrastructure.persistence.scan;

import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.port.outbound.ScanLock;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Row locks on a scan, taken after the project and consent locks (D-143). */
public final class JdbcScanLock implements ScanLock {

    private final JdbcClient jdbc;

    public JdbcScanLock(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Scan> noKeyUpdate(UUID scanId) {
        return jdbc.sql("SELECT " + ScanRows.COLUMNS + " FROM scan WHERE id = :id FOR NO KEY UPDATE")
                .param("id", scanId).query(ScanRows::map).optional();
    }

    @Override
    public Optional<Scan> share(UUID scanId) {
        return jdbc.sql("SELECT " + ScanRows.COLUMNS + " FROM scan WHERE id = :id FOR SHARE")
                .param("id", scanId).query(ScanRows::map).optional();
    }
}
