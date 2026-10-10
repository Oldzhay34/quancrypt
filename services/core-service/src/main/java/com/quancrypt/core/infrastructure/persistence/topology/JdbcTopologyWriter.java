package com.quancrypt.core.infrastructure.persistence.topology;

import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.TopologyWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Writes a scan's topology: one row, then nodes, links, call sites and finding links, each as one batch. */
public final class JdbcTopologyWriter implements TopologyWriter {

    private final JdbcClient jdbc;
    private final NamedParameterJdbcOperations batch;
    private final IdGenerator ids;

    public JdbcTopologyWriter(JdbcClient jdbc, NamedParameterJdbcOperations batch, IdGenerator ids) {
        this.jdbc = jdbc;
        this.batch = batch;
        this.ids = ids;
    }

    /** The cascade removes nodes, links, call sites and finding links with the topology row. */
    @Override
    public void deleteByScan(UUID scanId) {
        jdbc.sql("DELETE FROM topology WHERE scan_id = :scanId").param("scanId", scanId).update();
    }

    @Override
    public void insert(Topology topology) {
        jdbc.sql("INSERT INTO topology (id, scan_id, recorded_at) VALUES (:id, :scanId, :recordedAt)")
                .param("id", topology.id()).param("scanId", topology.scanId()).param("recordedAt", Sql.ts(topology.recordedAt()))
                .update();
        List<SqlParameterSource> nodes = new ArrayList<>();
        for (ServiceNode node : topology.nodes()) {
            nodes.add(new MapSqlParameterSource().addValue("id", node.id()).addValue("topologyId", topology.id())
                    .addValue("name", node.name()).addValue("kind", node.kind().name()));
        }
        run("INSERT INTO service_node (id, topology_id, name, node_kind) VALUES (:id, :topologyId, :name, :kind)", nodes);
        List<SqlParameterSource> links = new ArrayList<>();
        List<SqlParameterSource> callSites = new ArrayList<>();
        List<SqlParameterSource> findingLinks = new ArrayList<>();
        for (ServiceLink link : topology.links()) {
            links.add(new MapSqlParameterSource().addValue("id", link.id()).addValue("source", link.sourceNodeId())
                    .addValue("target", link.targetNodeId()).addValue("protocol", link.protocol().name())
                    .addValue("tls", link.tls()).addValue("mtls", link.mtls()));
            for (CallSite site : link.callSites()) {
                callSites.add(new MapSqlParameterSource().addValue("id", ids.next()).addValue("linkId", link.id())
                        .addValue("fileId", site.sourceFileId()).addValue("lineStart", site.lineStart()).addValue("lineEnd", site.lineEnd()));
            }
            for (UUID findingId : link.findingIds()) {
                findingLinks.add(new MapSqlParameterSource().addValue("linkId", link.id()).addValue("findingId", findingId));
            }
        }
        run("""
                INSERT INTO service_link (id, source_node_id, target_node_id, protocol, tls, mtls)
                VALUES (:id, :source, :target, :protocol, :tls, :mtls)""", links);
        run("""
                INSERT INTO link_call_site (id, link_id, source_file_id, line_start, line_end)
                VALUES (:id, :linkId, :fileId, :lineStart, :lineEnd)""", callSites);
        run("INSERT INTO link_finding (link_id, finding_id) VALUES (:linkId, :findingId)", findingLinks);
    }

    private void run(String sql, List<SqlParameterSource> rows) {
        if (!rows.isEmpty()) {
            batch.batchUpdate(sql, rows.toArray(SqlParameterSource[]::new));
        }
    }
}
