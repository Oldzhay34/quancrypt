package com.quancrypt.analyzer.facade.dto;

import java.util.List;

/** The service topology of a project (contracts/schemas/topology.schema.json). */
public record TopologyDto(List<NodeDto> nodes, List<EdgeDto> edges) {

    public TopologyDto {
        nodes = List.copyOf(nodes);
        edges = List.copyOf(edges);
    }

    /** Where a node or an edge was seen. */
    public record EvidenceDto(String file, Integer lineStart, Integer lineEnd, String locationKind) {
    }

    /** A node. */
    public record NodeDto(String id, String name, String kind, List<EvidenceDto> evidence) {

        public NodeDto {
            evidence = List.copyOf(evidence);
        }
    }

    /** An edge. */
    public record EdgeDto(String source, String target, String protocol, boolean tls, boolean mtls, List<EvidenceDto> evidence) {

        public EdgeDto {
            evidence = List.copyOf(evidence);
        }
    }
}
