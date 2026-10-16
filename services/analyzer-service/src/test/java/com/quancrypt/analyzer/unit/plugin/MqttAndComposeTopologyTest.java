package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/**
 * MQTT (MqttTopologyDetector: Mosquitto listeners, Paho clients, devices from compose) and compose files
 * (ComposeFileDetector: published ports, services outside the project, canonical names).
 */
class MqttAndComposeTopologyTest {

    private static final String MOSQUITTO = "listener 8883\ncertfile /mosquitto/certs/broker.crt.pem\nrequire_certificate true\n";
    private static final String PAHO = """
            import org.eclipse.paho.client.mqttv3.MqttClient;

            class Subscriber {
                private final Props props;
                Subscriber(Props props) throws Exception {
                    this.props = props;
                    MqttClient client = new MqttClient(props.brokerUrl(), "id");
                    client.subscribe("terminal/+/transactions");
                }
            }
            """;
    private static final String COMPOSE = """
            services:
              mosquitto:
                image: eclipse-mosquitto:2.0.22
                volumes:
                  - ./broker/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
              payment:
                build:
                  context: ./payment
                depends_on:
                  mosquitto:
                    condition: service_healthy
              terminal:
                build:
                  context: ./terminal
                volumes:
                  - ./certs/terminal.crt.pem:/certs/terminal.crt.pem:ro
                  - ./certs/terminal.key.pem:/certs/terminal.key.pem:ro
                depends_on:
                  mosquitto:
                    condition: service_healthy
              postgres:
                image: postgres:16
                ports:
                  - "127.0.0.1:5432:5432"
            """;

    private static ServiceGraph graph() {
        return TopologyHarness.graph("docker-compose.yml", COMPOSE, "broker/mosquitto.conf", MOSQUITTO,
                "payment/pom.xml", TopologyHarness.pom("25"),
                "payment/src/main/resources/application.yml", TopologyHarness.yaml("payment", "mqtt:\n  broker-url: ssl://localhost:8883\nspring:\n  ssl:\n    bundle:\n      pem:\n"
                        + "        mqttclient:\n          keystore:\n            certificate: file:/certs/payment.crt.pem\n            private-key: file:/certs/payment.key.pem\n"),
                "payment/src/main/java/Subscriber.java", PAHO + "\nclass Bundles { void b(org.springframework.boot.ssl.SslBundles b) { b.getBundle(\"mqttclient\"); } }\n",
                "terminal/main.py", "print('device')\n",
                "certs/broker.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/payment.crt.pem", TestPems.RSA_2048_CERTIFICATE,
                "certs/payment.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER, "certs/terminal.crt.pem", TestPems.RSA_2048_CERTIFICATE,
                "certs/terminal.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER);
    }

    @Test
    void theBrokerIsTheComposeServiceThatMountsTheMosquittoConfiguration() {
        ServiceGraph graph = graph();

        assertThat(TopologyHarness.node(graph, "mosquitto").kind()).isEqualTo(NodeKind.BROKER);
        assertThat(TopologyHarness.node(graph, "mosquitto").evidence()).extracting(e -> e.file().value()).contains("broker/mosquitto.conf", "docker-compose.yml");
    }

    @Test
    void aPahoClientIsAnMqttEdgeAndTheBrokerRequiringCertificatesMakesItMutualTls() {
        ServiceEdge edge = TopologyHarness.edge(graph(), "payment", "mosquitto");

        assertThat(edge.protocol()).isEqualTo(Protocol.MQTT);
        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).isTrue();
        assertThat(edge.evidence()).extracting(e -> e.file().value()).contains("payment/src/main/java/Subscriber.java");
        assertThat(edge.keyExchange()).isPresent();
    }

    @Test
    void aComposeServiceWithoutSpringThatMountsACertificateAndItsKeyIsADeviceOfTheBroker() {
        ServiceGraph graph = graph();

        assertThat(TopologyHarness.node(graph, "terminal").kind()).isEqualTo(NodeKind.DEVICE);
        ServiceEdge edge = TopologyHarness.edge(graph, "terminal", "mosquitto");
        assertThat(edge.protocol()).isEqualTo(Protocol.MQTT);
        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).isTrue();
        assertThat(edge.keyExchange()).as("a device is not a Java client of the project").isEmpty();
        assertThat(edge.findings()).extracting(f -> f.file().value()).contains("certs/terminal.crt.pem", "certs/broker.crt.pem");
    }

    @Test
    void aBrokerWithoutRequireCertificateIsTlsButNotMutual() {
        ServiceGraph graph = TopologyHarness.graph("docker-compose.yml", COMPOSE, "broker/mosquitto.conf", "listener 8883\ncertfile /certs/broker.crt.pem\n",
                "terminal/main.py", "x = 1\n", "certs/broker.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/terminal.crt.pem", TestPems.RSA_2048_CERTIFICATE,
                "certs/terminal.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER);

        ServiceEdge edge = TopologyHarness.edge(graph, "terminal", "mosquitto");
        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).isFalse();
    }

    @Test
    void aServiceThatTheProjectDoesNotContainIsNotANodeUnlessAKeptEdgeReachesIt() {
        ServiceGraph graph = graph();

        assertThat(graph.nodes()).extracting(n -> n.id()).doesNotContain("postgres");
    }

    @Test
    void aPublishedPortOfASpringServiceIsAnEdgeFromTheExternalClient() {
        String compose = "services:\n  web:\n    build:\n      context: ./web\n    ports:\n      - \"8443:8443\"\n";
        ServiceGraph graph = TopologyHarness.graph("docker-compose.yml", compose, "web/pom.xml", TopologyHarness.pom("17"),
                "web/src/main/resources/application.yml", TopologyHarness.yaml("web-app", "server:\n  port: 8443\n  ssl:\n    bundle: web\n"));

        ServiceEdge edge = TopologyHarness.edge(graph, "external-client", "web");
        assertThat(edge.protocol()).isEqualTo(Protocol.HTTP);
        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).isFalse();
        assertThat(TopologyHarness.node(graph, "external-client").kind()).isEqualTo(NodeKind.EXTERNAL);
        assertThat(graph.nodes()).extracting(n -> n.id()).as("the compose name wins over the application name").doesNotContain("web-app");
    }

    @Test
    void withoutComposeTheApplicationNameIsTheNodeIdAndAUrlHostInAnyOfTheNamesFindsIt() {
        ServiceGraph graph = TopologyHarness.graph("svc-dir/pom.xml", TopologyHarness.pom("17"),
                "svc-dir/src/main/resources/application.yml", TopologyHarness.yaml("billing-app", "server:\n  port: 8082\n"),
                "caller/pom.xml", TopologyHarness.pom("17"),
                "caller/src/main/resources/application.yml", TopologyHarness.yaml("caller", "a:\n  url: http://svc-dir:8082\nb:\n  url: http://billing-app:8082\n"));

        assertThat(graph.nodes()).extracting(n -> n.id()).containsExactly("billing-app", "caller");
        assertThat(TopologyHarness.edge(graph, "caller", "billing-app").evidence()).hasSize(2);
    }
}
