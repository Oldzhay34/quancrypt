package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.port.inbound.GetTopologyQuery;
import com.quancrypt.core.port.inbound.GetTopologyUseCase;
import com.quancrypt.core.port.inbound.view.TopologyView;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.SourceFileReader;
import com.quancrypt.core.port.outbound.TopologyReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Reads the topology of a scan with the files of its call sites. */
public final class GetTopologyService implements GetTopologyUseCase {

    private final TransactionRunner tx;
    private final TopologyReader topologies;
    private final SourceFileReader files;

    public GetTopologyService(TransactionRunner tx, TopologyReader topologies, SourceFileReader files) {
        this.tx = tx;
        this.topologies = topologies;
        this.files = files;
    }

    @Override
    public TopologyView execute(GetTopologyQuery input) {
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Topology topology = topologies.find(input.scanId()).orElseThrow(() -> Fail.notFound("topology"));
            Set<UUID> fileIds = topology.links().stream()
                    .flatMap(l -> l.callSites().stream()).map(CallSite::sourceFileId).collect(Collectors.toSet());
            return ViewMapper.topology(topology, files.byIds(fileIds));
        });
    }
}
