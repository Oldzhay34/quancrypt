package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.model.AnalysisStats;
import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.FindingRef;
import com.quancrypt.analyzer.domain.model.KeyExchange;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.PluginInfo;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.domain.model.Snippet;
import com.quancrypt.analyzer.port.inbound.AnalysisView;
import com.quancrypt.analyzer.port.inbound.CbomView;
import com.quancrypt.analyzer.port.inbound.EdgeView;
import com.quancrypt.analyzer.port.inbound.EvidenceView;
import com.quancrypt.analyzer.port.inbound.FindingRefView;
import com.quancrypt.analyzer.port.inbound.FindingView;
import com.quancrypt.analyzer.port.inbound.KeyExchangeView;
import com.quancrypt.analyzer.port.inbound.NodeView;
import com.quancrypt.analyzer.port.inbound.PluginView;
import com.quancrypt.analyzer.port.inbound.ProjectView;
import com.quancrypt.analyzer.port.inbound.RuntimeView;
import com.quancrypt.analyzer.port.inbound.SnippetLineView;
import com.quancrypt.analyzer.port.inbound.SnippetView;
import com.quancrypt.analyzer.port.inbound.StatsView;
import com.quancrypt.analyzer.port.inbound.TopologyView;
import java.util.List;
import java.util.UUID;

/** Maps domain values to the inbound port views, which carry codes as strings (the facade does not see the domain). */
final class Views {

    private Views() {
    }

    static ProjectView project(ProjectDescriptor project) {
        return new ProjectView(project.root().value(), project.type().name());
    }

    static AnalysisView analysis(UUID id, ProjectDescriptor project, RuntimeInfo runtime, List<CryptoUsage> usages, Cbom cbom,
            AnalysisStats stats) {
        return new AnalysisView(id, project.type().name(), new RuntimeView(runtime.javaVersion(), runtime.springBootVersion()),
                usages.stream().map(Views::finding).toList(), new CbomView(cbom.specVersion(), cbom.json()),
                new StatsView(stats.filesScanned(), stats.findingsTotal(), stats.durationMs()));
    }

    static FindingView finding(CryptoUsage usage) {
        CryptoAlgorithm algorithm = usage.algorithm();
        Evidence evidence = usage.evidence();
        return new FindingView(evidence.file().value(), evidence.lines().map(LineRange::start), evidence.lines().map(LineRange::end),
                algorithm.rawName(), usage.symbol(), algorithm.family().name(), algorithm.mode(), algorithm.padding(), algorithm.hash(),
                algorithm.keySizeBits(), usage.usageContext().name(), evidence.locationKind().name(), usage.priority().name(),
                usage.library(), usage.confidence(), usage.detectorId());
    }

    static TopologyView topology(ServiceGraph graph) {
        return new TopologyView(graph.nodes().stream().map(Views::node).toList(), graph.edges().stream().map(Views::edge).toList());
    }

    static SnippetView snippet(Snippet snippet) {
        return new SnippetView(snippet.path().value(),
                snippet.lines().stream().map(line -> new SnippetLineView(line.number(), line.text())).toList());
    }

    static PluginView plugin(PluginInfo info) {
        return new PluginView(info.id(), info.name(), info.version(), info.projectTypes().stream().map(Enum::name).sorted().toList());
    }

    private static NodeView node(ServiceNode node) {
        return new NodeView(node.id(), node.name(), node.kind().name(), evidence(node.evidence()));
    }

    private static EdgeView edge(ServiceEdge edge) {
        return new EdgeView(edge.source(), edge.target(), edge.protocol().name(), edge.tls(), edge.mtls(), evidence(edge.evidence()),
                edge.findings().stream().map(Views::findingRef).toList(), edge.keyExchange().map(Views::keyExchange));
    }

    private static FindingRefView findingRef(FindingRef ref) {
        return new FindingRefView(ref.file().value(), ref.symbol(), ref.algorithmFamily().name(), ref.usageContext().name(), ref.lineStart());
    }

    private static KeyExchangeView keyExchange(KeyExchange exchange) {
        return new KeyExchangeView(exchange.groupFamily().name(), exchange.groups(), exchange.inferred(), exchange.confidence());
    }

    private static List<EvidenceView> evidence(List<Evidence> evidence) {
        return evidence.stream().map(e -> new EvidenceView(e.file().value(), e.lines().map(LineRange::start),
                e.lines().map(LineRange::end), e.locationKind().name())).toList();
    }
}
