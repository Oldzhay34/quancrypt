package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.BuildRuntime;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSources;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Builds the service topology of a project (FR-08): finds the modules and compose services, lets every topology detector
 * report the connections it sees, and assembles the graph with the crypto of each edge.
 *
 * <p>The Java files that may hold a connection (the analysis names them by a cheap text check) are parsed one at a time: each is
 * handed to every {@link UnitTopologyDetector}, its module facts are collected, and the syntax tree is dropped before the next
 * file, so memory does not grow with the number of such files. Every step passes a checkpoint of the time budget (D-199), and the
 * number of connections the detectors may report is limited before the graph is built (D-194g, D-181).
 */
public final class TopologyBuilder {

    /** Connections the detectors may report for one project; a project with more is not read further. */
    static final int MAX_RAW_EDGES = 50_000;

    private final BuildRuntime runtime;
    private final JavaSources sources;
    private final ComposeFileDetector compose;
    private final List<UnitTopologyDetector> unitDetectors;
    private final List<TopologyDetector> detectors;

    public TopologyBuilder(BuildRuntime runtime, JavaSources sources, SpringConfigReader configReader) {
        this.runtime = runtime;
        this.sources = sources;
        this.compose = new ComposeFileDetector(configReader);
        MqttTopologyDetector mqtt = new MqttTopologyDetector();
        this.unitDetectors = List.of(new HttpClientCallDetector(), new FeignClientDetector(), mqtt, new GrpcChannelDetector());
        this.detectors = List.of(new SpringClientConfigDetector(), new GatewayRouteDetector(), mqtt, new MessagingConfigDetector(), compose,
                new KubernetesManifestDetector());
    }

    /**
     * The topology of the project the index describes, with the crypto usages already found in it and the Java files that mention
     * something the topology detectors look for.
     */
    public ServiceGraph build(SourceTree tree, ProjectIndex index, List<CryptoUsage> usages, List<ProjectFile> javaFiles) {
        tree.checkpoint();
        Modules modules = Modules.discover(index, runtime);
        List<ComposeService> composeServices = compose.read(index);
        ServiceRegistry registry = new ServiceIdentityResolver().resolve(index, modules, composeServices);
        ModuleFacts facts = new ModuleFacts();
        TopologyContext context = new TopologyContext(index, modules, composeServices, registry, facts);
        List<RawEdge> edges = new ArrayList<>();
        TopologySink sink = edge -> {
            if (edges.size() >= MAX_RAW_EDGES) {
                throw new SourceTooLargeException("the project has more connections than one topology reads");
            }
            edges.add(edge);
        };
        for (ProjectFile file : javaFiles) {
            tree.checkpoint();
            Optional<JavaUnit> unit = sources.parse(tree, file);
            if (unit.isEmpty()) {
                continue;
            }
            modules.of(file.path()).ifPresent(module -> facts.collect(module, unit.get()));
            for (UnitTopologyDetector detector : unitDetectors) {
                detector.detect(context, unit.get(), sink);
            }
        }
        for (TopologyDetector detector : detectors) {
            tree.checkpoint();
            detector.detect(context, sink);
        }
        tree.checkpoint();
        return new TopologyAssembler().assemble(context, edges, usages, tree);
    }
}
