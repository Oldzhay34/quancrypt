package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Topology;
import java.util.UUID;

/** Writes topologies. */
public interface TopologyWriter {

    /** Deletes the scan's topology, nodes, links, call sites and finding links, if any. */
    void deleteByScan(UUID scanId);

    void insert(Topology topology);
}
