package com.quancrypt.core.infrastructure.persistence.finding;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.FindingFilter;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingStats;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads findings joined with their source file; the scan is reached through the file (no scan_id on finding, D-131). */
public final class JdbcFindingReader implements FindingReader {

    /** Starts with a space: it is appended to a FROM clause. */
    private static final String FILTER = " " + """
             WHERE sf.scan_id = :scanId
               AND (CAST(:priority AS varchar) IS NULL OR f.priority = :priority)
               AND (CAST(:algorithm AS varchar) IS NULL OR f.algorithm_family = :algorithm)
               AND (CAST(:usage AS varchar) IS NULL OR f.usage_context = :usage)
               AND (CAST(:kind AS varchar) IS NULL OR sf.location_kind = :kind)
               AND (CAST(:classifiedBy AS varchar) IS NULL OR f.classified_by = :classifiedBy)""";

    private final JdbcClient jdbc;

    public JdbcFindingReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<FindingDetail> find(UUID findingId) {
        return jdbc.sql(FindingRows.SELECT_DETAIL + " WHERE f.id = :id").param("id", findingId).query(FindingRows::detail).optional();
    }

    @Override
    public PageResult<FindingDetail> page(UUID scanId, FindingFilter filter, int page, int size) {
        List<FindingDetail> items = filtered(FindingRows.SELECT_DETAIL + FILTER + FindingRows.ORDER + " LIMIT :size OFFSET :offset", scanId, filter)
                .param("size", size).param("offset", Sql.offset(page, size))
                .query(FindingRows::detail).list();
        long total = filtered("SELECT count(*) FROM finding f JOIN source_file sf ON sf.id = f.source_file_id" + FILTER, scanId, filter)
                .query(Long.class).single();
        return new PageResult<>(items, page, size, total);
    }

    private JdbcClient.StatementSpec filtered(String sql, UUID scanId, FindingFilter filter) {
        return jdbc.sql(sql)
                .param("scanId", scanId)
                .param("priority", filter.priority().map(Enum::name).orElse(null))
                .param("algorithm", filter.algorithmFamily().map(Enum::name).orElse(null))
                .param("usage", filter.usageContext().map(Enum::name).orElse(null))
                .param("kind", filter.locationKind().map(Enum::name).orElse(null))
                .param("classifiedBy", filter.classifiedBy().map(Enum::name).orElse(null));
    }

    @Override
    public int countByScan(UUID scanId) {
        return jdbc.sql("SELECT count(*) FROM finding f JOIN source_file sf ON sf.id = f.source_file_id WHERE sf.scan_id = :scanId")
                .param("scanId", scanId).query(Integer.class).single();
    }

    @Override
    public List<FindingDetail> listByScan(UUID scanId) {
        return jdbc.sql(FindingRows.SELECT_DETAIL + " WHERE sf.scan_id = :scanId" + FindingRows.ORDER)
                .param("scanId", scanId).query(FindingRows::detail).list();
    }

    /** One GROUPING SETS query yields the counts by priority, algorithm family and location kind. */
    @Override
    public FindingStats stats(UUID scanId) {
        Map<Priority, Integer> byPriority = new EnumMap<>(Priority.class);
        Map<AlgorithmFamily, Integer> byAlgorithm = new EnumMap<>(AlgorithmFamily.class);
        Map<LocationKind, Integer> byKind = new EnumMap<>(LocationKind.class);
        jdbc.sql("""
                SELECT f.priority, f.algorithm_family, sf.location_kind, count(*) AS n
                FROM finding f JOIN source_file sf ON sf.id = f.source_file_id
                WHERE sf.scan_id = :scanId
                GROUP BY GROUPING SETS ((f.priority), (f.algorithm_family), (sf.location_kind))""")
                .param("scanId", scanId)
                .query(rs -> {
                    int n = rs.getInt("n");
                    String priority = rs.getString("priority");
                    String algorithm = rs.getString("algorithm_family");
                    String kind = rs.getString("location_kind");
                    if (priority != null) {
                        byPriority.put(Priority.valueOf(priority), n);
                    } else if (algorithm != null) {
                        byAlgorithm.put(AlgorithmFamily.valueOf(algorithm), n);
                    } else if (kind != null) {
                        byKind.put(LocationKind.valueOf(kind), n);
                    }
                });
        int total = byPriority.values().stream().mapToInt(Integer::intValue).sum();
        return new FindingStats(total, byPriority, byAlgorithm, byKind);
    }
}
