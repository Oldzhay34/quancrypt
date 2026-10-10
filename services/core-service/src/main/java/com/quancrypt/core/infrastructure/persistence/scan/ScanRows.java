package com.quancrypt.core.infrastructure.persistence.scan;

import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.infrastructure.persistence.Sql;
import java.sql.ResultSet;
import java.sql.SQLException;

/** Column list and row mapping of the scan table. */
final class ScanRows {

    static final String COLUMNS = "id, project_id, runtime_profile_sequence_no, status, started_at, completed_at";

    private ScanRows() {
    }

    static Scan map(ResultSet rs, int rowNum) throws SQLException {
        return new Scan(
                Sql.uuid(rs, "id"),
                Sql.uuid(rs, "project_id"),
                Sql.optInt(rs, "runtime_profile_sequence_no"),
                Sql.code(rs, "status", ScanStatus.class),
                Sql.instant(rs, "started_at"),
                Sql.optInstant(rs, "completed_at"));
    }
}
