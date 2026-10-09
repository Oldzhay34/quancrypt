package com.quancrypt.core.port.inbound;

import java.util.List;
import java.util.UUID;

/** Replaces the topology of a running scan. */
public record RecordTopologyCommand(UUID scanId, List<NodeInput> nodes, List<LinkInput> links, String caller) {

    public RecordTopologyCommand {
        nodes = List.copyOf(nodes);
        links = List.copyOf(links);
    }
}
