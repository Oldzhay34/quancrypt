package com.quancrypt.core.facade.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** Topology (schema Topology). */
public record TopologyDto(UUID scanId, Instant recordedAt, List<NodeDto> nodes, List<LinkDto> links) {

    public TopologyDto {
        nodes = nodes == null ? null : List.copyOf(nodes);
        links = links == null ? null : List.copyOf(links);
    }
}

