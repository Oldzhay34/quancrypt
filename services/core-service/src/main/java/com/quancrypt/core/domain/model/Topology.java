package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/** The service topology of one scan: nodes and links; validates the same-topology invariants (D-131). */
public record Topology(UUID id, UUID scanId, Instant recordedAt, List<ServiceNode> nodes, List<ServiceLink> links) {

    public Topology {
        nodes = List.copyOf(nodes);
        links = List.copyOf(links);
        Set<String> names = new HashSet<>();
        Set<UUID> nodeIds = new HashSet<>();
        for (ServiceNode node : nodes) {
            if (!names.add(node.name()) || !nodeIds.add(node.id())) {
                throw new IllegalArgumentException("node names must be unique within a topology");
            }
        }
        Set<String> edges = new HashSet<>();
        for (ServiceLink link : links) {
            if (!nodeIds.contains(link.sourceNodeId()) || !nodeIds.contains(link.targetNodeId())) {
                throw new IllegalArgumentException("both ends of a link must be nodes of the same topology");
            }
            if (!edges.add(link.sourceNodeId() + ">" + link.targetNodeId() + ":" + link.protocol())) {
                throw new IllegalArgumentException("duplicate link between the same nodes and protocol");
            }
        }
    }

    /** True when the link has a device at one end. */
    public boolean isDeviceLink(ServiceLink link) {
        return nodes.stream()
                .anyMatch(n -> n.kind() == NodeKind.DEVICE && (n.id().equals(link.sourceNodeId()) || n.id().equals(link.targetNodeId())));
    }
}
