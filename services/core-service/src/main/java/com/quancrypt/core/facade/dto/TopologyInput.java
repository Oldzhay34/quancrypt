package com.quancrypt.core.facade.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** Body of RecordTopology (schema TopologyInput). */
public record TopologyInput(@NotNull @Size(max = 200) List<@NotNull @Valid NodeInputDto> nodes, @NotNull @Size(max = 1000) List<@NotNull @Valid LinkInputDto> links) {

    public TopologyInput {
        nodes = nodes == null ? null : List.copyOf(nodes);
        links = links == null ? null : List.copyOf(links);
    }
}

