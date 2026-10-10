package com.quancrypt.core.infrastructure.persistence.finding;

import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.port.outbound.FindingWriter;
import java.math.BigDecimal;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

/**
 * Inserts findings as one batch; uq_finding_location (NULLS NOT DISTINCT) skips duplicates. The batch's per-row update
 * counts (1 inserted, 0 skipped) tell which ids were inserted, so no RETURNING round trip per row is needed.
 */
public final class JdbcFindingWriter implements FindingWriter {

    private static final String INSERT = """
            INSERT INTO finding (id, source_file_id, symbol, algorithm_family, usage_context, priority, key_size_bits,
                                 line_start, line_end, confidence, classified_by)
            VALUES (:id, :sourceFileId, :symbol, :algorithm, :usage, :priority, :keySize, :lineStart, :lineEnd, :confidence,
                    :classifiedBy)
            ON CONFLICT ON CONSTRAINT uq_finding_location DO NOTHING""";

    private final NamedParameterJdbcOperations batch;

    public JdbcFindingWriter(NamedParameterJdbcOperations batch) {
        this.batch = batch;
    }

    @Override
    public List<UUID> insertIgnoringDuplicates(List<Finding> findings) {
        if (findings.isEmpty()) {
            return List.of();
        }
        SqlParameterSource[] rows = findings.stream().map(JdbcFindingWriter::row).toArray(SqlParameterSource[]::new);
        int[] counts = batch.batchUpdate(INSERT, rows);
        List<UUID> inserted = new ArrayList<>();
        for (int i = 0; i < counts.length; i++) {
            if (counts[i] == 1) {
                inserted.add(findings.get(i).id());
            } else if (counts[i] != 0) {
                throw new IllegalStateException("the driver did not report a row count for the finding batch");
            }
        }
        return inserted;
    }

    private static SqlParameterSource row(Finding f) {
        return new MapSqlParameterSource()
                .addValue("id", f.id())
                .addValue("sourceFileId", f.sourceFileId())
                .addValue("symbol", f.symbol())
                .addValue("algorithm", f.algorithm().name())
                .addValue("usage", f.usage().name())
                .addValue("priority", f.priority().name())
                .addValue("keySize", f.keySizeBits().orElse(null), Types.INTEGER)
                .addValue("lineStart", f.lineStart().orElse(null), Types.INTEGER)
                .addValue("lineEnd", f.lineEnd().orElse(null), Types.INTEGER)
                .addValue("confidence", BigDecimal.valueOf(f.confidence()))
                .addValue("classifiedBy", f.classifiedBy().name());
    }
}
