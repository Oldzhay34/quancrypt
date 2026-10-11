package com.quancrypt.analyzer.domain.model;

import java.util.List;
import java.util.Objects;

/** A connection from the node that opens it (client) to the node that listens (server). mTLS implies TLS. */
public record ServiceEdge(String source, String target, Protocol protocol, boolean tls, boolean mtls, List<Evidence> evidence) {

    public ServiceEdge {
        Text.matching(source, Text.NODE_ID, "source");
        Text.matching(target, Text.NODE_ID, "target");
        Objects.requireNonNull(protocol, "protocol");
        if (mtls && !tls) {
            throw new IllegalArgumentException("an mTLS edge is also a TLS edge");
        }
        evidence = List.copyOf(evidence);
        if (evidence.size() > ServiceNode.MAX_EVIDENCE) {
            throw new IllegalArgumentException("an edge has at most 100 evidence entries");
        }
    }
}
