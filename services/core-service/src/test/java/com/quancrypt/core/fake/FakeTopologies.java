package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.port.outbound.TopologyReader;
import com.quancrypt.core.port.outbound.TopologyWriter;
import java.util.Optional;
import java.util.UUID;

/** Topologies, one per scan. */
public final class FakeTopologies implements TopologyReader, TopologyWriter {

    private final InMemoryDatabase db;

    public FakeTopologies(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<Topology> find(UUID scanId) {
        return Optional.ofNullable(db.topologies.get(scanId));
    }

    @Override
    public boolean exists(UUID scanId) {
        return db.topologies.containsKey(scanId);
    }

    @Override
    public void deleteByScan(UUID scanId) {
        db.topologies.remove(scanId);
    }

    @Override
    public void insert(Topology topology) {
        if (db.topologies.containsKey(topology.scanId())) {
            throw new IllegalStateException("a scan has one topology");
        }
        db.topologies.put(topology.scanId(), topology);
    }
}
