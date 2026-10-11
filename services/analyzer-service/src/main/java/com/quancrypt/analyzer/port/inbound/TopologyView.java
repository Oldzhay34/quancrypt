package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** The service topology of a project. */
public record TopologyView(List<NodeView> nodes, List<EdgeView> edges) {

    public TopologyView {
        nodes = List.copyOf(nodes);
        edges = List.copyOf(edges);
    }
}
