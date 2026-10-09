package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.TopologyRecorded;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.NodeKind;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RecordTopologyUseCase;
import com.quancrypt.core.port.inbound.view.TopologyView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.SourceFileWriter;
import com.quancrypt.core.port.outbound.TopologyReader;
import com.quancrypt.core.port.outbound.TopologyWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Replaces the topology of a running scan and tells the warehouse the first time (D-139c, D-146). */
public final class RecordTopologyService implements RecordTopologyUseCase {

    static final int MAX_NODES = 200;
    static final int MAX_LINKS = 1000;
    static final int MAX_CALL_SITES = 100;
    static final int MAX_FINDING_IDS = 500;

    private final TransactionRunner tx;
    private final ScanAccess access;
    private final SourceFileResolver resolver;
    private final SourceFileWriter sourceFileWriter;
    private final FindingReader findingReader;
    private final TopologyReader topologyReader;
    private final TopologyWriter topologyWriter;
    private final EventRecorder events;
    private final AuditRecorder audit;
    private final Clock clock;
    private final IdGenerator ids;

    public RecordTopologyService(
            TransactionRunner tx, ScanAccess access, SourceFileResolver resolver, SourceFileWriter sourceFileWriter,
            FindingReader findingReader, TopologyReader topologyReader, TopologyWriter topologyWriter, EventRecorder events,
            AuditRecorder audit, Clock clock, IdGenerator ids) {
        this.tx = tx;
        this.access = access;
        this.resolver = resolver;
        this.sourceFileWriter = sourceFileWriter;
        this.findingReader = findingReader;
        this.topologyReader = topologyReader;
        this.topologyWriter = topologyWriter;
        this.events = events;
        this.audit = audit;
        this.clock = clock;
        this.ids = ids;
    }

    @Override
    public TopologyView execute(RecordTopologyCommand input) {
        if (input.nodes().size() > MAX_NODES || input.links().size() > MAX_LINKS) {
            throw Fail.validation("a topology holds at most " + MAX_NODES + " nodes and " + MAX_LINKS + " links");
        }
        CallerKind caller = Codes.caller(input.caller());
        for (LinkInput link : input.links()) {
            if (link.callSites().size() > MAX_CALL_SITES || link.findingIds().size() > MAX_FINDING_IDS) {
                throw Fail.validation("a link holds at most " + MAX_CALL_SITES + " call sites and " + MAX_FINDING_IDS + " findings");
            }
        }
        List<PathKind> callSiteFiles = new ArrayList<>();
        for (LinkInput link : input.links()) {
            for (CallSiteInput cs : link.callSites()) {
                callSiteFiles.add(new PathKind(cs.path(), Codes.parse(LocationKind.class, cs.locationKind(), "locationKind")));
            }
        }
        Map<String, LocationKind> kinds = SourceFileResolver.kindsByPath(callSiteFiles);
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            LockedScan locked = access.runningForUpdate(input.scanId());
            UUID scanId = locked.scan().id();
            Set<UUID> scanFindings = findingReader.listByScan(scanId).stream().map(d -> d.finding().id()).collect(Collectors.toSet());
            boolean first = !topologyReader.exists(scanId);
            topologyWriter.deleteByScan(scanId);
            sourceFileWriter.deleteUnreferenced(scanId);
            Map<String, SourceFile> files = resolver.resolve(scanId, kinds);
            Topology topology = Guard.valid(() -> build(scanId, input, files, scanFindings));
            topologyWriter.insert(topology);
            if (first) {
                List<TopologyRecorded.LinkSummary> summaries = topology.links().stream()
                        .map(l -> new TopologyRecorded.LinkSummary(l.protocol(), l.tls(), l.mtls())).toList();
                events.recordIfConsented(locked.warehouseConsent(), locked.project().key(), new TopologyRecorded(topology.nodes().size(), topology.links().size(), summaries));
            }
            audit.record(AuditAction.TOPOLOGY_RECORDED, Optional.of(locked.project().key()), Optional.of(scanId), caller);
            Map<UUID, SourceFile> byId = files.values().stream().collect(Collectors.toMap(SourceFile::id, f -> f));
            return ViewMapper.topology(topology, byId);
        });
    }

    private Topology build(UUID scanId, RecordTopologyCommand input, Map<String, SourceFile> files, Set<UUID> scanFindings) {
        Map<String, ServiceNode> nodes = new LinkedHashMap<>();
        for (NodeInput n : input.nodes()) {
            NodeKind kind = Codes.parse(NodeKind.class, n.nodeKind(), "nodeKind");
            if (nodes.put(n.name(), new ServiceNode(ids.next(), n.name(), kind)) != null) {
                throw new IllegalArgumentException("node names must be unique within a topology");
            }
        }
        List<ServiceLink> links = new ArrayList<>();
        for (LinkInput l : input.links()) {
            ServiceNode source = nodes.get(l.source());
            ServiceNode target = nodes.get(l.target());
            if (source == null || target == null) {
                throw new IllegalArgumentException("both ends of a link must be nodes of the topology");
            }
            for (UUID findingId : l.findingIds()) {
                if (!scanFindings.contains(findingId)) {
                    throw new IllegalArgumentException("a link may only use findings of the same scan");
                }
            }
            List<CallSite> callSites = l.callSites().stream()
                    .map(cs -> new CallSite(files.get(cs.path()).id(), cs.lineStart(), cs.lineEnd())).toList();
            links.add(new ServiceLink(ids.next(), source.id(), target.id(), Codes.parse(Protocol.class, l.protocol(), "protocol"),
                    l.tls(), l.mtls(), callSites, new HashSet<>(l.findingIds())));
        }
        return new Topology(ids.next(), scanId, clock.now(), List.copyOf(nodes.values()), links);
    }
}
