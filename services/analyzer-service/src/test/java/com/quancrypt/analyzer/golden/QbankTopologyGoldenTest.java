package com.quancrypt.analyzer.golden;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.evaluation.TopologyEvaluation;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.TreeSet;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * The topology of the QBank reference system against the approved golden file (D-123, D-209; H2): the same nodes, the same
 * edges with protocol, TLS and mutual TLS, for every edge the findings of the certificates the golden file names, and the
 * inferred key exchange of the Java clients. The comparison itself is {@link TopologyEvaluation}, the code the evaluation
 * report uses. Measured values of the golden file (cipher suite, negotiated group) are not produced by static analysis and
 * are not compared (see the class comment there).
 */
class QbankTopologyGoldenTest {

    private static TopologyEvaluation.Run run;

    @BeforeAll
    static void analyze() throws Exception {
        CanonicalNames names = new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
        run = TopologyEvaluation.run(JavaSpringPlugins.standard(names), Path.of(System.getProperty("quancrypt.reference.dir")),
                Path.of(System.getProperty("quancrypt.expected.dir")));
    }

    @Test
    void theNodesAreTheOnesOfTheGoldenFile() {
        assertThat(run.nodeDifferences()).isEmpty();
        assertThat(run.graph().nodes()).hasSize(run.goldenNodes().size());
    }

    @Test
    void theEdgesCarryTheProtocolTlsAndMutualTlsOfTheGoldenFile() {
        assertThat(run.edgeDifferences()).isEmpty();
        assertThat(run.graph().edges()).hasSize(run.goldenEdges().size());
    }

    @Test
    void everyEdgeNamesTheFindingsOfTheCertificatesOfTheGoldenFile() {
        assertThat(run.findingGaps()).isEmpty();
    }

    @Test
    void theKeyExchangeOfAJavaClientIsInferredAndOffersTheGroupThatWasMeasured() {
        assertThat(run.keyExchangeDifferences()).isEmpty();
        long inferred = run.graph().edges().stream().filter(e -> e.keyExchange().isPresent()).count();
        assertThat(inferred).as("edges with an inferred key exchange").isEqualTo(run.goldenEdges().stream().filter(e -> e.measuredGroup().isPresent()).count());
        assertThat(inferred).isPositive();
    }

    @Test
    void anEdgeHasTlsFactsOnlyWhenItIsTls() {
        for (ServiceEdge edge : run.graph().edges()) {
            if (!edge.tls()) {
                assertThat(edge.findings()).isEmpty();
                assertThat(edge.keyExchange()).isEmpty();
            }
        }
    }

    @Test
    void theGraphIsSortedAndItsIdsAreUnique() {
        assertThat(new TreeSet<>(run.graph().nodes().stream().map(ServiceNode::id).toList())).hasSameSizeAs(run.graph().nodes());
        assertThat(run.graph().edges()).isSortedAccordingTo(Comparator.comparing(ServiceEdge::source).thenComparing(ServiceEdge::target)
                .thenComparing(e -> e.protocol().name()));
    }

    @Test
    void theDeviceEdgeComesFromComposeAndMutualTlsFromTheMountedCertificate() {
        ServiceEdge device = run.edge("terminal-001", "mosquitto").orElseThrow();

        assertThat(device.source()).isEqualTo("field-device-sim");
        assertThat(device.tls()).isTrue();
        assertThat(device.mtls()).isTrue();
        assertThat(device.evidence()).extracting(e -> e.file().value()).containsOnly("docker-compose.yml");
    }
}
