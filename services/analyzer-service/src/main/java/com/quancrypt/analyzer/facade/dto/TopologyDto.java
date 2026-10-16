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

    /** The natural key of a finding an edge uses (D-208). */
    public record FindingRefDto(String file, String symbol, String algorithmFamily, String usageContext, Integer lineStart) {
    }

    /** The inferred key exchange of a TLS edge (D-208). */
    public record KeyExchangeDto(String groupFamily, List<String> groups, boolean inferred, double confidence) {

        public KeyExchangeDto {
            groups = List.copyOf(groups);
        }
    }

    /** An edge; {@code keyExchange} is null for an edge without TLS or without an inference. */
    public record EdgeDto(String source, String target, String protocol, boolean tls, boolean mtls, List<EvidenceDto> evidence,
            List<FindingRefDto> findings, KeyExchangeDto keyExchange) {

        public EdgeDto {
            evidence = List.copyOf(evidence);
            findings = List.copyOf(findings);
        }

        /** An edge without crypto details. */
        public EdgeDto(String source, String target, String protocol, boolean tls, boolean mtls, List<EvidenceDto> evidence) {
            this(source, target, protocol, tls, mtls, evidence, List.of(), null);
        }
    }
}
