package com.quancrypt.analyzer.domain.model;

import java.util.List;
import java.util.Objects;

/** A node of the service graph: a part of the project or an endpoint it talks to. */
public record ServiceNode(String id, String name, NodeKind kind, List<Evidence> evidence) {

    public static final int MAX_EVIDENCE = 100;

    public ServiceNode {
        Text.matching(id, Text.NODE_ID, "id");
        Text.printable(name, 200, "name");
        Objects.requireNonNull(kind, "kind");
        evidence = List.copyOf(evidence);
        if (evidence.size() > MAX_EVIDENCE) {
            throw new IllegalArgumentException("a node has at most 100 evidence entries");
        }
    }
}
