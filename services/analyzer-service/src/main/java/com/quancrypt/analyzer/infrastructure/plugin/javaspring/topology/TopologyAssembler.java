package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;

/**
 * Turns what the detectors saw into the graph: targets are resolved to nodes, connections with the same ends and protocol are
 * merged (their evidence, client bundles and client certificates are added up), connections that do not start in the project
 * are dropped (a service of the compose file that the project does not contain has no known calls), and the
 * {@link EdgeCryptoMapper} adds the TLS facts. A node is in the graph when the project contains it or a kept connection reaches
 * it. Everything is sorted, so the same project gives the same graph.
 */
final class TopologyAssembler {

    ServiceGraph assemble(TopologyContext context, List<RawEdge> raw, List<CryptoUsage> usages, SourceTree tree) {
        ServiceRegistry registry = context.registry();
        EdgeCryptoMapper mapper = new EdgeCryptoMapper(context, usages);
        Map<String, MergedEdge> merged = new TreeMap<>();
        for (RawEdge edge : raw) {
            tree.checkpoint();
            Optional<TNode> source = source(registry, edge);
            if (source.isEmpty() || (!source.get().present && !source.get().id.equals(TopologySink.EXTERNAL_CLIENT))) {
                continue;
            }
            TNode target = registry.resolve(edge.target(), edge.protocol());
            if (target == source.get()) {
                continue;
            }
            String key = source.get().id + "\u0000" + target.id + "\u0000" + edge.protocol();
            merged.computeIfAbsent(key, k -> new MergedEdge(source.get(), target, edge.protocol())).add(edge);
            if (merged.size() > ServiceGraph.MAX_EDGES) {
                throw new SourceTooLargeException("the project has more connections than one topology holds");
            }
        }
        Set<TNode> included = new LinkedHashSet<>();
        registry.all().stream().filter(n -> n.present).forEach(included::add);
        List<ServiceEdge> edges = new ArrayList<>();
        for (MergedEdge edge : merged.values()) {
            tree.checkpoint();
            EdgeCryptoMapper.Result crypto = mapper.map(edge, edge.source(), edge.target());
            included.add(edge.source());
            if (edge.source().id.equals(TopologySink.EXTERNAL_CLIENT)) {
                edge.evidence().forEach(edge.source()::addEvidence);
            }
            included.add(edge.target());
            edges.add(new ServiceEdge(edge.source().id, edge.target().id, edge.protocol(), crypto.tls(), crypto.mtls(), edge.sortedEvidence(), crypto.findings(),
                    crypto.keyExchange()));
        }
        List<ServiceNode> nodes = included.stream().sorted(Comparator.comparing((TNode n) -> n.id)).map(TopologyAssembler::node).toList();
        if (nodes.size() > ServiceGraph.MAX_NODES || edges.size() > ServiceGraph.MAX_EDGES) {
            throw new SourceTooLargeException("the project has more services or connections than one topology holds");
        }
        return new ServiceGraph(nodes, edges);
    }

    private static Optional<TNode> source(ServiceRegistry registry, RawEdge edge) {
        if (edge.sourceId().equals(TopologySink.EXTERNAL_CLIENT)) {
            TNode node = registry.declare(TopologySink.EXTERNAL_CLIENT, NodeKind.EXTERNAL, true);
            node.present = false;
            return Optional.of(node);
        }
        return registry.byId(edge.sourceId());
    }

    private static ServiceNode node(TNode node) {
        return new ServiceNode(node.id, node.id, node.kind, node.evidence);
    }

    /** Connections with the same ends and protocol, added up. */
    static final class MergedEdge {

        private final TNode source;
        private final TNode target;
        private final Protocol protocol;
        /** Whether every connection seen between the two ends is encrypted: one plain connection is not hidden by an encrypted one. */
        private boolean allTls = true;
        private final Set<Integer> targetPorts = new LinkedHashSet<>();
        private final List<Evidence> evidence = new ArrayList<>();
        private final Set<String> bundles = new LinkedHashSet<>();
        private final Set<String> certificates = new LinkedHashSet<>();

        MergedEdge(TNode source, TNode target, Protocol protocol) {
            this.source = source;
            this.target = target;
            this.protocol = protocol;
        }

        void add(RawEdge edge) {
            allTls &= edge.tls();
            targetPorts.add(edge.target().port());
            for (Evidence one : edge.evidence()) {
                if (!evidence.contains(one) && evidence.size() < ServiceNode.MAX_EVIDENCE) {
                    evidence.add(one);
                }
            }
            bundles.addAll(edge.clientBundles());
            certificates.addAll(edge.clientCertificates());
        }

        TNode source() {
            return source;
        }

        TNode target() {
            return target;
        }

        Protocol protocol() {
            return protocol;
        }

        boolean tls() {
            return allTls;
        }

        /** The port every connection goes to, or -1 when none is written or they differ. */
        int targetPort() {
            return targetPorts.size() == 1 ? targetPorts.iterator().next() : -1;
        }

        List<Evidence> evidence() {
            return evidence;
        }

        Set<String> bundles() {
            return bundles;
        }

        Set<String> certificates() {
            return certificates;
        }

        List<Evidence> sortedEvidence() {
            return evidence.stream().sorted(Comparator.comparing((Evidence e) -> e.file().value())
                    .thenComparingInt(e -> e.lines().map(LineRange::start).orElse(0))).toList();
        }
    }
}
