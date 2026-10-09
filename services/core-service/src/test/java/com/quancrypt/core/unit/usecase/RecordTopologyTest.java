package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.GetTopologyQuery;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.view.CallSiteView;
import com.quancrypt.core.port.inbound.view.LinkView;
import com.quancrypt.core.port.inbound.view.NodeView;
import com.quancrypt.core.port.inbound.view.TopologyView;
import java.util.List;
import java.util.UUID;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

import static com.quancrypt.core.fake.Problems.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

class RecordTopologyTest {

    private final World w = new World();

    private static NodeInput node(String name, String kind) {
        return new NodeInput(name, kind);
    }

    private static LinkInput link(String source, String target, String protocol, boolean tls, boolean mtls, List<CallSiteInput> sites, List<UUID> findings) {
        return new LinkInput(source, target, protocol, tls, mtls, sites, findings);
    }

    private static CallSiteInput site(String path, int line, String kind) {
        return new CallSiteInput(path, line, line, kind);
    }

    private TopologyView put(UUID scanId, List<NodeInput> nodes, List<LinkInput> links) {
        return w.recordTopology.execute(new RecordTopologyCommand(scanId, nodes, links, "INTERNAL"));
    }

    private UUID scan() {
        return w.runningScan(w.projectWithWarehouseConsent());
    }

    @Test
    void aTopologyIsStoredWithNamedNodesCallSitesAndTheirFiles() {
        UUID scanId = scan();
        UUID finding = w.record(scanId, World.tlsFinding("src/Client.java", "Client#call")).createdIds().get(0);
        w.db.lockLog.clear();
        TopologyView view = put(scanId, List.of(node("gateway", "GATEWAY"), node("account", "SERVICE")),
                List.of(link("gateway", "account", "HTTP", true, true, List.of(site("src/Client.java", 12, "CODE"), site("src/Other.java", 3, "CODE")), List.of(finding))));
        assertThat(view.nodes()).extracting(NodeView::name).containsExactly("gateway", "account");
        LinkView stored = view.links().get(0);
        assertThat(stored.source()).isEqualTo("gateway");
        assertThat(stored.mtls()).isTrue();
        assertThat(stored.callSites()).extracting(CallSiteView::path).containsExactly("src/Client.java", "src/Other.java");
        assertThat(stored.findingIds()).containsExactly(finding);
        assertThat(w.db.sourceFiles).hasSize(2);
        assertThat(w.db.lockLog).containsExactly("project:keyShare", "consent:share", "scan:noKeyUpdate");
        assertThat(w.getTopology.execute(new GetTopologyQuery(scanId)).links()).hasSize(1);
    }

    @Test
    void theFirstTopologyWritesOneEventAndAReplacementWritesNone() {
        UUID scanId = scan();
        put(scanId, List.of(node("a", "SERVICE"), node("b", "SERVICE")), List.of(link("a", "b", "GRPC", true, false, List.of(), List.of())));
        put(scanId, List.of(node("a", "SERVICE"), node("c", "SERVICE")), List.of(link("a", "c", "GRPC", true, false, List.of(), List.of())));
        assertThat(w.outboxTypes()).containsExactly(EventType.TOPOLOGY_RECORDED);
        assertThat(w.outbox().get(0).payload()).containsEntry("node_count", 2).containsEntry("link_count", 1);
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.TOPOLOGY_RECORDED)).hasSize(2);
        assertThat(w.db.topologies.get(scanId).nodes()).extracting(ServiceNode::name).containsExactly("a", "c");
    }

    @Test
    void withoutConsentThereIsNoEvent() {
        UUID scanId = w.runningScan(w.project());
        put(scanId, List.of(node("a", "SERVICE")), List.of());
        assertThat(w.outbox()).isEmpty();
    }

    @Test
    void brokenTopologiesAreValidationFailures() {
        UUID scanId = scan();
        List<NodeInput> nodes = List.of(node("a", "SERVICE"), node("b", "SERVICE"));
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "ghost", "HTTP", true, false, List.of(), List.of()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, List.of(node("a", "SERVICE"), node("a", "GATEWAY")), List.of()), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "a", "HTTP", true, false, List.of(), List.of()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "b", "HTTP", false, true, List.of(), List.of()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "b", "HTTP", true, false, List.of(), List.of()),
                link("a", "b", "HTTP", true, true, List.of(), List.of()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, List.of(node("a", "ROBOT")), List.of()), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "b", "FAX", true, false, List.of(), List.of()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "b", "HTTP", true, false, List.of(), List.of(new UUID(9, 9))))), ProblemCode.VALIDATION_FAILED);
        assertThat(w.db.topologies).isEmpty();
    }

    @Test
    void sizeLimitsAreEnforced() {
        UUID scanId = scan();
        List<NodeInput> manyNodes = IntStream.range(0, 201).mapToObj(i -> node("n" + i, "SERVICE")).toList();
        assertProblem(() -> put(scanId, manyNodes, List.of()), ProblemCode.VALIDATION_FAILED);
        List<CallSiteInput> manySites = IntStream.range(1, 102).mapToObj(i -> site("src/A.java", i, "CODE")).toList();
        assertProblem(() -> put(scanId, List.of(node("a", "SERVICE"), node("b", "SERVICE")),
                List.of(link("a", "b", "HTTP", true, false, manySites, List.of()))), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aFindingOfAnotherScanCannotBeLinked() {
        UUID projectId = w.projectWithWarehouseConsent();
        UUID first = w.runningScan(projectId);
        UUID foreign = w.record(first, World.tlsFinding("src/A.java", "A#x")).createdIds().get(0);
        w.complete(first);
        UUID second = w.runningScan(projectId);
        assertProblem(() -> put(second, List.of(node("a", "SERVICE"), node("b", "SERVICE")),
                List.of(link("a", "b", "HTTP", true, false, List.of(), List.of(foreign)))), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aFileKeepsItsKindAcrossFindingsAndCallSites() {
        UUID scanId = scan();
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        List<NodeInput> nodes = List.of(node("a", "SERVICE"), node("b", "SERVICE"));
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "b", "HTTP", true, false, List.of(site("src/A.java", 1, "CONFIG")), List.of()))),
                ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> put(scanId, nodes, List.of(link("a", "b", "HTTP", true, false,
                List.of(site("src/N.java", 1, "CODE"), site("src/N.java", 2, "CONFIG")), List.of()))), ProblemCode.VALIDATION_FAILED);
    }

    @Test
    void aReplacementDropsFilesNothingPointsToAnymoreSoTheirKindCanBeCorrected() {
        UUID scanId = scan();
        w.record(scanId, World.tlsFinding("src/A.java", "A#x"));
        List<NodeInput> nodes = List.of(node("a", "SERVICE"), node("b", "SERVICE"));
        put(scanId, nodes, List.of(link("a", "b", "HTTP", true, false, List.of(site("conf/app.yml", 1, "CODE")), List.of())));
        put(scanId, nodes, List.of(link("a", "b", "HTTP", true, false, List.of(site("conf/app.yml", 1, "CONFIG")), List.of())));
        assertThat(w.db.sourceFiles.values()).filteredOn(f -> f.path().equals("conf/app.yml")).singleElement()
                .satisfies(f -> assertThat(f.locationKind()).isEqualTo(LocationKind.CONFIG));
        put(scanId, nodes, List.of());
        assertThat(w.db.sourceFiles.values()).extracting(SourceFile::path).containsExactly("src/A.java");
    }

    @Test
    void aScanThatIsNotRunningOrUnknownRejectsATopology() {
        UUID scanId = scan();
        w.complete(scanId);
        assertProblem(() -> put(scanId, List.of(node("a", "SERVICE")), List.of()), ProblemCode.SCAN_NOT_RUNNING);
        assertProblem(() -> put(new UUID(9, 9), List.of(node("a", "SERVICE")), List.of()), ProblemCode.NOT_FOUND);
        assertProblem(() -> w.getTopology.execute(new GetTopologyQuery(scanId)), ProblemCode.NOT_FOUND);
    }
}
