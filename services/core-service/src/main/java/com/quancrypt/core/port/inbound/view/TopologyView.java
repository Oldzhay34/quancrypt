package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** The topology of a scan. */
public record TopologyView(UUID scanId, Instant recordedAt, List<NodeView> nodes, List<LinkView> links) {

    public TopologyView {
        nodes = List.copyOf(nodes);
        links = List.copyOf(links);
    }
}
