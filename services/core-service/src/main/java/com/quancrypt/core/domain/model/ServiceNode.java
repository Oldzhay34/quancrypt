package com.quancrypt.core.domain.model;

import java.util.UUID;

/** A node of the service topology. */
public record ServiceNode(UUID id, String name, NodeKind kind) {

    public ServiceNode {
        if (name == null || name.isBlank() || name.length() > 200) {
            throw new IllegalArgumentException("node name must be 1..200 characters");
        }
    }
}
