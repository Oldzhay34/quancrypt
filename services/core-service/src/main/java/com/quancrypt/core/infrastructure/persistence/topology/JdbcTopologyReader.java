package com.quancrypt.core.infrastructure.persistence.topology;

import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.NodeKind;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.TopologyReader;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads a scan's topology with five queries (topology, nodes, links, call sites, finding links), whatever its size. */
public final class JdbcTopologyReader implements TopologyReader {

    private final JdbcClient jdbc;

    public JdbcTopologyReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    private record Head(UUID id, Instant recordedAt) {
    }

    private record LinkRow(UUID id, UUID source, UUID target, Protocol protocol, boolean tls, boolean mtls) {
    }

    @Override
    public boolean exists(UUID scanId) {
        return jdbc.sql("SELECT EXISTS (SELECT 1 FROM topology WHERE scan_id = :scanId)").param("scanId", scanId)
                .query(Boolean.class).single();
    }

    @Override
    public Optional<Topology> find(UUID scanId) {
        Optional<Head> head = jdbc.sql("SELECT id, recorded_at FROM topology WHERE scan_id = :scanId").param("scanId", scanId)
                .query((rs, n) -> new Head(Sql.uuid(rs, "id"), Sql.instant(rs, "recorded_at"))).optional();
        return head.map(h -> load(scanId, h));
    }

    private Topology load(UUID scanId, Head head) {
        List<ServiceNode> nodes = jdbc.sql("SELECT id, name, node_kind FROM service_node WHERE topology_id = :id ORDER BY name")
                .param("id", head.id())
                .query((rs, n) -> new ServiceNode(Sql.uuid(rs, "id"), rs.getString("name"), Sql.code(rs, "node_kind", NodeKind.class)))
                .list();
        List<LinkRow> links = jdbc.sql("""
                SELECT l.id, l.source_node_id, l.target_node_id, l.protocol, l.tls, l.mtls
                FROM service_link l JOIN service_node s ON s.id = l.source_node_id
                WHERE s.topology_id = :id ORDER BY l.id""")
                .param("id", head.id())
                .query((rs, n) -> new LinkRow(Sql.uuid(rs, "id"), Sql.uuid(rs, "source_node_id"), Sql.uuid(rs, "target_node_id"),
                        Sql.code(rs, "protocol", Protocol.class), rs.getBoolean("tls"), rs.getBoolean("mtls")))
                .list();
        Map<UUID, List<CallSite>> callSites = new HashMap<>();
        jdbc.sql("""
                SELECT cs.link_id, cs.source_file_id, cs.line_start, cs.line_end
                FROM link_call_site cs JOIN service_link l ON l.id = cs.link_id JOIN service_node s ON s.id = l.source_node_id
                WHERE s.topology_id = :id ORDER BY cs.link_id, cs.line_start, cs.source_file_id""")
                .param("id", head.id())
                .query(rs -> {
                    callSites.computeIfAbsent(Sql.uuid(rs, "link_id"), k -> new ArrayList<>())
                            .add(new CallSite(Sql.uuid(rs, "source_file_id"), rs.getInt("line_start"), rs.getInt("line_end")));
                });
        Map<UUID, Set<UUID>> findings = new HashMap<>();
        jdbc.sql("""
                SELECT lf.link_id, lf.finding_id
                FROM link_finding lf JOIN service_link l ON l.id = lf.link_id JOIN service_node s ON s.id = l.source_node_id
                WHERE s.topology_id = :id""")
                .param("id", head.id())
                .query(rs -> {
                    findings.computeIfAbsent(Sql.uuid(rs, "link_id"), k -> new HashSet<>()).add(Sql.uuid(rs, "finding_id"));
                });
        List<ServiceLink> serviceLinks = links.stream()
                .map(l -> new ServiceLink(l.id(), l.source(), l.target(), l.protocol(), l.tls(), l.mtls(),
                        callSites.getOrDefault(l.id(), List.of()), findings.getOrDefault(l.id(), Set.of())))
                .toList();
        return new Topology(head.id(), scanId, head.recordedAt(), nodes, serviceLinks);
    }
}
