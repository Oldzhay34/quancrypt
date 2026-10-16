package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/**
 * The cases of the P3.4 architecture review that decide whether an edge tells the truth: listeners are read one by one, a plain
 * connection is not hidden by an encrypted one, an outside host is not a service of the project, a device needs an identity, and
 * the HTTP clients named by the prompt (RestTemplate, WebClient) are recognised.
 */
class TopologyCorrectnessTest {

    private static final String BROKER = "listener 1883\n\nlistener 8883\ncertfile /certs/broker.crt.pem\nrequire_certificate true\n";
    private static final String BUNDLE = "mqtt:\n  ssl:\n    bundle: mtls\nspring:\n  ssl:\n    bundle:\n      pem:\n        mtls:\n          keystore:\n"
            + "            certificate: file:/certs/client.crt.pem\n            private-key: file:/certs/client.key.pem\n";

    @Test
    void eachListenerOfABrokerSpeaksForItsOwnPort() {
        ServiceGraph graph = TopologyHarness.graph("broker/mosquitto.conf", BROKER,
                "plain/pom.xml", TopologyHarness.pom("17"), "plain/src/main/resources/application.yml", TopologyHarness.yaml("plain", "mqtt-url: tcp://broker:1883\n"),
                "secure/pom.xml", TopologyHarness.pom("17"),
                "secure/src/main/resources/application.yml", TopologyHarness.yaml("secure", "mqtt-url: ssl://broker:8883\n" + BUNDLE),
                "certs/broker.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/client.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        ServiceEdge plain = TopologyHarness.edge(graph, "plain", "broker");
        assertThat(plain.protocol()).isEqualTo(Protocol.MQTT);
        assertThat(plain.tls()).as("the plain 1883 listener has no certificate").isFalse();
        assertThat(plain.mtls()).isFalse();
        ServiceEdge secure = TopologyHarness.edge(graph, "secure", "broker");
        assertThat(secure.tls()).isTrue();
        assertThat(secure.mtls()).isTrue();
    }

    @Test
    void aPlainConnectionIsNotHiddenByAnEncryptedOneToTheSameService() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "one:\n  url: http://b:8080\ntwo:\n  url: https://b:8443\n"),
                "b/pom.xml", TopologyHarness.pom("17"), "b/src/main/resources/application.yml", TopologyHarness.yaml("b", ""));

        ServiceEdge edge = TopologyHarness.edge(graph, "a", "b");
        assertThat(edge.tls()).isFalse();
        assertThat(edge.evidence()).hasSize(2);
    }

    @Test
    void anOutsideHostIsNeverTakenForAServiceOfTheProjectThatSharesItsFirstLabel() {
        ServiceGraph graph = TopologyHarness.graph("auth/pom.xml", TopologyHarness.pom("17"),
                "auth/src/main/resources/application.yml", TopologyHarness.yaml("auth", "server:\n  port: 9000\n"),
                "web/pom.xml", TopologyHarness.pom("17"),
                "web/src/main/resources/application.yml", TopologyHarness.yaml("web", "oidc:\n  issuer: https://auth.partner.com/\ninternal:\n  url: http://auth.shop.svc.cluster.local:9000\n"));

        assertThat(TopologyHarness.edge(graph, "web", "auth.partner.com").tls()).isTrue();
        assertThat(TopologyHarness.edge(graph, "web", "auth").tls()).as("a cluster-internal name is the service").isFalse();
    }

    @Test
    void aSecureSchemeInABrokerAddressIsTls() {
        ServiceGraph graph = TopologyHarness.graph("orders/pom.xml", TopologyHarness.pom("17"),
                "orders/src/main/resources/application.yml", TopologyHarness.yaml("orders", "spring:\n  rabbitmq:\n    addresses: amqps://mq:5671\n"));

        assertThat(TopologyHarness.edge(graph, "orders", "mq-5671").tls()).isTrue();
    }

    @Test
    void aComposeServiceThatDependsOnABrokerWithoutAnIdentityIsNotADevice() {
        String compose = "services:\n  mosquitto:\n    image: eclipse-mosquitto:2.0.22\n  worker:\n    build:\n      context: ./worker\n    depends_on:\n      - mosquitto\n";
        ServiceGraph graph = TopologyHarness.graph("docker-compose.yml", compose, "worker/main.py", "print(1)\n");

        TopologyHarness.assertNoEdge(graph, "worker", "mosquitto");
        assertThat(graph.nodes()).extracting(n -> n.id()).contains("worker");
    }

    @Test
    void restTemplateWebClientAndUrlLiteralsAreHttpClientEdges() {
        String java = """
                import org.springframework.web.client.RestTemplate;
                import org.springframework.web.reactive.function.client.WebClient;

                class Clients {
                    private final Props props;
                    Clients(Props props) {
                        this.props = props;
                        new RestTemplate().getForObject("https://literal.example.com:9443/ping", String.class);
                        WebClient.create(props.peerUrl());
                    }
                }
                """;
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "peer-url: http://peer:8081\n"), "a/src/main/java/Clients.java", java);

        ServiceEdge literal = TopologyHarness.edge(graph, "a", "literal.example.com-9443");
        assertThat(literal.tls()).isTrue();
        assertThat(literal.evidence().get(0).file().value()).isEqualTo("a/src/main/java/Clients.java");
        ServiceEdge peer = TopologyHarness.edge(graph, "a", "peer-8081");
        assertThat(peer.evidence()).extracting(e -> e.file().value()).contains("a/src/main/java/Clients.java", "a/src/main/resources/application.yml");
    }

    @Test
    void manyPropertiesAreMappedInTimeThatGrowsWithTheirNumberAndNotWithItsSquare() {
        StringBuilder config = new StringBuilder();
        for (int i = 0; i < 15_000; i++) {
            config.append("k").append(i).append("-url: https://host").append(i % 40).append(".example.org/p").append(i).append('\n');
        }
        String java = "import org.springframework.web.client.RestTemplate;\n\nclass C {\n    void a(Props p) { new RestTemplate().getForObject(p.k7Url(), String.class); }\n}\n";
        long start = System.nanoTime();
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", config.toString(), "a/src/main/java/C.java", java);

        assertThat(graph.edges()).hasSize(40);
        assertThat((System.nanoTime() - start) / 1_000_000_000L).as("seconds").isLessThan(30);
    }

    @Test
    void aSecretInTheUserInformationOfAConfiguredUrlIsNotInTheGraph() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "db:\n  url: https://admin:P@ssw0rd@db.internal/x\n"));

        assertThat(graph.nodes()).extracting(n -> n.id()).contains("db.internal").noneMatch(id -> id.contains("ssw0rd"));
        assertThat(graph.edges()).noneMatch(e -> e.target().contains("ssw0rd"));
    }

    @Test
    void moreNodesThanOneTopologyHoldsFailTheAnalysisInsteadOfTruncatingIt() {
        StringBuilder urls = new StringBuilder();
        for (int i = 0; i < 250; i++) {
            urls.append("u").append(i).append(":\n  url: https://host").append(i).append(".example.com\n");
        }
        assertThatThrownBy(() -> TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", urls.toString()))).isInstanceOf(SourceTooLargeException.class);
    }
}
