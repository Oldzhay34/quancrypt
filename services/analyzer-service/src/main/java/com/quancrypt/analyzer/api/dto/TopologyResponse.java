package com.quancrypt.analyzer.api.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.quancrypt.analyzer.facade.dto.TopologyDto;
import java.util.List;

/**
 * The body of BuildTopology. An edge without a key exchange leaves the field out (the contract's `key_exchange` is optional
 * and an object, never null); every other field is always written, evidence lines included (they may be null).
 */
public record TopologyResponse(List<TopologyDto.NodeDto> nodes, List<EdgeResponse> edges) {

    public TopologyResponse {
        nodes = List.copyOf(nodes);
        edges = List.copyOf(edges);
    }

    public static TopologyResponse of(TopologyDto dto) {
        return new TopologyResponse(dto.nodes(), dto.edges().stream().map(EdgeResponse::of).toList());
    }

    /** An edge of the response. */
    public record EdgeResponse(String source, String target, String protocol, boolean tls, boolean mtls,
            List<TopologyDto.EvidenceDto> evidence, List<TopologyDto.FindingRefDto> findings,
            @JsonInclude(JsonInclude.Include.NON_NULL) TopologyDto.KeyExchangeDto keyExchange) {

        public EdgeResponse {
            evidence = List.copyOf(evidence);
            findings = List.copyOf(findings);
        }

        static EdgeResponse of(TopologyDto.EdgeDto edge) {
            return new EdgeResponse(edge.source(), edge.target(), edge.protocol(), edge.tls(), edge.mtls(), edge.evidence(), edge.findings(),
                    edge.keyExchange());
        }
    }
}
