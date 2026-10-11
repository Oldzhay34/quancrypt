package com.quancrypt.analyzer.domain.model;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** The service topology: unique nodes and edges whose ends are nodes of the graph (topology.schema.json limits). */
public record ServiceGraph(List<ServiceNode> nodes, List<ServiceEdge> edges) {

    public static final int MAX_NODES = 200;
    public static final int MAX_EDGES = 1000;
    public static final ServiceGraph EMPTY = new ServiceGraph(List.of(), List.of());

    public ServiceGraph {
        nodes = List.copyOf(nodes);
        edges = List.copyOf(edges);
        if (nodes.size() > MAX_NODES || edges.size() > MAX_EDGES) {
            throw new IllegalArgumentException("a graph has at most 200 nodes and 1000 edges");
        }
        Set<String> ids = new HashSet<>();
        for (ServiceNode node : nodes) {
            if (!ids.add(node.id())) {
                throw new IllegalArgumentException("node ids are unique");
            }
        }
        for (ServiceEdge edge : edges) {
            if (!ids.contains(edge.source()) || !ids.contains(edge.target())) {
                throw new IllegalArgumentException("both ends of an edge are nodes of the graph");
            }
        }
    }
}
