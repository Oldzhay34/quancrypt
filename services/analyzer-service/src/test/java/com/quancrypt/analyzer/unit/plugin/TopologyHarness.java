package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;

/** Builds the topology of a small in-memory project with the standard Java plugin. */
final class TopologyHarness {

    private TopologyHarness() {
    }

    /** The topology of the project made of the given path and content pairs. */
    static ServiceGraph graph(String... pathsAndContents) {
        return JavaSpringPlugins.standard(DetectorHarness.names()).buildTopology(DetectorHarness.tree(pathsAndContents));
    }

    /** A Maven build file that names a Java version (the module and its Java version for the inference). */
    static String pom(String javaVersion) {
        return "<project><properties><java.version>" + javaVersion + "</java.version></properties></project>";
    }

    /** A Spring configuration file with the application name and the given YAML lines below it. */
    static String yaml(String applicationName, String rest) {
        return "spring:\n  application:\n    name: " + applicationName + "\n" + rest;
    }

    static ServiceNode node(ServiceGraph graph, String id) {
        return graph.nodes().stream().filter(n -> n.id().equals(id)).findFirst()
                .orElseThrow(() -> new AssertionError("no node " + id + " in " + graph.nodes().stream().map(ServiceNode::id).toList()));
    }

    static ServiceEdge edge(ServiceGraph graph, String source, String target) {
        return graph.edges().stream().filter(e -> e.source().equals(source) && e.target().equals(target)).findFirst()
                .orElseThrow(() -> new AssertionError("no edge " + source + " -> " + target + " in "
                        + graph.edges().stream().map(e -> e.source() + "->" + e.target()).toList()));
    }

    static void assertNoEdge(ServiceGraph graph, String source, String target) {
        assertThat(graph.edges()).noneMatch(e -> e.source().equals(source) && e.target().equals(target));
    }
}
