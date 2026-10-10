package com.quancrypt.core.infrastructure.persistence.finding;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.infrastructure.persistence.Sql;
import java.sql.ResultSet;
import java.sql.SQLException;

/** Select lists and row mappings of findings (joined with their source file) and of source files. */
final class FindingRows {

    static final String SELECT_DETAIL = """
            SELECT f.id, f.source_file_id, f.symbol, f.algorithm_family, f.usage_context, f.priority, f.key_size_bits,
                   f.line_start, f.line_end, f.confidence, f.classified_by,
                   sf.scan_id, sf.path, sf.location_kind
            FROM finding f JOIN source_file sf ON sf.id = f.source_file_id""";

    /** Stable order of a scan's findings: file, line, symbol. */
    static final String ORDER = " ORDER BY sf.path, f.line_start NULLS FIRST, f.symbol, f.id";

    static final String SOURCE_FILE_COLUMNS = "id, scan_id, path, location_kind";

    private FindingRows() {
    }

    static FindingDetail detail(ResultSet rs, int rowNum) throws SQLException {
        Finding finding = new Finding(
                Sql.uuid(rs, "id"),
                Sql.uuid(rs, "source_file_id"),
                rs.getString("symbol"),
                Sql.code(rs, "algorithm_family", AlgorithmFamily.class),
                Sql.code(rs, "usage_context", UsageContext.class),
                Sql.code(rs, "priority", Priority.class),
                Sql.optInt(rs, "key_size_bits"),
                Sql.optInt(rs, "line_start"),
                Sql.optInt(rs, "line_end"),
                rs.getBigDecimal("confidence").doubleValue(),
                Sql.code(rs, "classified_by", ClassifiedBy.class));
        SourceFile file = new SourceFile(finding.sourceFileId(), Sql.uuid(rs, "scan_id"), rs.getString("path"),
                Sql.code(rs, "location_kind", LocationKind.class));
        return new FindingDetail(finding, file);
    }

    static SourceFile sourceFile(ResultSet rs, int rowNum) throws SQLException {
        return new SourceFile(Sql.uuid(rs, "id"), Sql.uuid(rs, "scan_id"), rs.getString("path"),
                Sql.code(rs, "location_kind", LocationKind.class));
    }
}
