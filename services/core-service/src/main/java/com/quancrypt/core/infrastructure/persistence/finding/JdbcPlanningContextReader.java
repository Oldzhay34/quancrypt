package com.quancrypt.core.infrastructure.persistence.finding;

import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.FindingContext;
import com.quancrypt.core.port.outbound.PlanningContextReader;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * Reads, in one query, whether each finding of a scan sits on a link with a DEVICE end (D-148) and how many call sites
 * its links have (D-124; the same count as v_finding_call_site_count, restricted to the scan).
 */
public final class JdbcPlanningContextReader implements PlanningContextReader {

    private final JdbcClient jdbc;

    public JdbcPlanningContextReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Map<UUID, FindingContext> load(UUID scanId) {
        Map<UUID, FindingContext> context = new HashMap<>();
        jdbc.sql("""
                SELECT f.id,
                       EXISTS (SELECT 1
                               FROM link_finding lf
                               JOIN service_link l ON l.id = lf.link_id
                               JOIN service_node s ON s.id = l.source_node_id
                               JOIN service_node t ON t.id = l.target_node_id
                               WHERE lf.finding_id = f.id AND (s.node_kind = 'DEVICE' OR t.node_kind = 'DEVICE')) AS on_device,
                       (SELECT count(cs.id)
                        FROM link_finding lf JOIN link_call_site cs ON cs.link_id = lf.link_id
                        WHERE lf.finding_id = f.id) AS call_sites
                FROM finding f JOIN source_file sf ON sf.id = f.source_file_id
                WHERE sf.scan_id = :scanId""")
                .param("scanId", scanId)
                .query(rs -> {
                    context.put(Sql.uuid(rs, "id"), new FindingContext(rs.getBoolean("on_device"), rs.getInt("call_sites")));
                });
        return context;
    }
}
