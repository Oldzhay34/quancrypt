package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/** The second security review of P3.4: bundle references, broker ports, and hosts that only look like services of the project. */
class TopologyHardeningTest {

    @Test
    void manyBundleReferencesAndManyUrlsAreMatchedByIndexAndEachEdgeKeepsFewBundles() {
        StringBuilder config = new StringBuilder();
        for (int i = 0; i < 6000; i++) {
            config.append("a.b.c.u").append(i).append("-url: https://h").append(i % 30).append(".example.org/\n");
            config.append("a.b.c.r").append(i).append(".ssl-bundle: bundle").append(i).append('\n');
        }
        long start = System.nanoTime();
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", config.toString());

        assertThat(graph.edges()).hasSize(30);
        assertThat((System.nanoTime() - start) / 1_000_000_000L).as("seconds").isLessThan(20);
    }

    @Test
    void aPortThatNoListenerClaimsIsNotGivenTheTlsOfAnotherListener() {
        String conf = "port 1883\n\nlistener 8883\ncertfile /certs/broker.crt.pem\nrequire_certificate true\n";
        ServiceGraph graph = TopologyHarness.graph("broker/mosquitto.conf", conf,
                "plain/pom.xml", TopologyHarness.pom("17"), "plain/src/main/resources/application.yml", TopologyHarness.yaml("plain", "mqtt-url: tcp://broker:1883\n"),
                "other/pom.xml", TopologyHarness.pom("17"), "other/src/main/resources/application.yml", TopologyHarness.yaml("other", "mqtt-url: tcp://broker:1884\n"),
                "certs/broker.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        ServiceEdge plain = TopologyHarness.edge(graph, "plain", "broker");
        assertThat(plain.tls()).as("port 1883 is the plain listener").isFalse();
        assertThat(plain.findings()).isEmpty();
        assertThat(TopologyHarness.edge(graph, "other", "broker").tls()).as("no listener claims 1884").isFalse();
    }

    @Test
    void aHostThatOnlyContainsSvcIsNotAServiceOfTheProject() {
        ServiceGraph graph = TopologyHarness.graph("billing/pom.xml", TopologyHarness.pom("17"),
                "billing/src/main/resources/application.yml", TopologyHarness.yaml("billing", "server:\n  port: 9000\n"),
                "web/pom.xml", TopologyHarness.pom("17"),
                "web/src/main/resources/application.yml", TopologyHarness.yaml("web", "x:\n  url: https://billing.svc.attacker.com/\n"));

        assertThat(TopologyHarness.edge(graph, "web", "billing.svc.attacker.com").tls()).isTrue();
        TopologyHarness.assertNoEdge(graph, "web", "billing");
    }

    @Test
    void anUrlWhoseUserInformationEndIsAGuessIsNoTarget() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "x:\n  url: https://u5:Sl@sh/Secret5@slash.internal/\n"));

        assertThat(graph.nodes()).extracting(n -> n.id()).containsExactly("a");
        assertThat(graph.edges()).isEmpty();
    }
}
