package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** A topology node. */
public record NodeView(String id, String name, String kind, List<EvidenceView> evidence) {

    public NodeView {
        evidence = List.copyOf(evidence);
    }
}
