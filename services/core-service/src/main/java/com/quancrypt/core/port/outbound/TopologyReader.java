package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Topology;
import java.util.Optional;
import java.util.UUID;

/** Reads topologies. */
public interface TopologyReader {

    Optional<Topology> find(UUID scanId);

    boolean exists(UUID scanId);
}
