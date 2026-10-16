package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/**
 * Service to service calls: URLs in configuration (SpringClientConfigDetector), gateway routes (GatewayRouteDetector), HTTP clients
 * in code (HttpClientCallDetector) and Feign clients (FeignClientDetector), and how TLS and mutual TLS follow from both ends.
 */
class ServiceCallsTopologyTest {

    private static final String SERVER_WITH_MTLS = """
            server:
              port: 9444
              ssl:
                bundle: server
                client-auth: need
            spring:
              ssl:
                bundle:
                  pem:
                    server:
                      keystore:
                        certificate: file:/certs/server.crt.pem
                        private-key: file:/certs/server.key.pem
            """;

    @Test
    void aUrlInConfigurationIsAnEdgeToTheServiceThatListensThere() {
        ServiceGraph graph = TopologyHarness.graph(
                "a/pom.xml", TopologyHarness.pom("17"), "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "billing:\n  url: http://b:8081/api\n"),
                "b/pom.xml", TopologyHarness.pom("17"), "b/src/main/resources/application.yml", TopologyHarness.yaml("b", "server:\n  port: 8081\n"));

        ServiceEdge edge = TopologyHarness.edge(graph, "a", "b");
        assertThat(edge.protocol()).isEqualTo(Protocol.HTTP);
        assertThat(edge.tls()).isFalse();
        assertThat(edge.mtls()).isFalse();
        assertThat(edge.evidence()).hasSize(1);
        assertThat(edge.evidence().get(0).lines().orElseThrow().start()).isEqualTo(5);
    }

    @Test
    void aLocalAddressIsResolvedByThePortOfTheOnlyServiceThatListensOnIt() {
        ServiceGraph graph = TopologyHarness.graph(
                "a/pom.xml", TopologyHarness.pom("17"), "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "peer:\n  url: https://localhost:9444\n"),
                "b/pom.xml", TopologyHarness.pom("17"), "b/src/main/resources/application.yml", TopologyHarness.yaml("b", SERVER_WITH_MTLS),
                "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        ServiceEdge edge = TopologyHarness.edge(graph, "a", "b");
        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).as("the client presents no identity").isFalse();
    }

    @Test
    void anUnknownHostBecomesAnExternalNodeWithoutCredentials() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "payments:\n  url: https://user:secret@pay.example.com:8443/v1\n"));

        ServiceEdge edge = TopologyHarness.edge(graph, "a", "pay.example.com-8443");
        assertThat(edge.tls()).isTrue();
        assertThat(TopologyHarness.node(graph, "pay.example.com-8443").kind()).isEqualTo(NodeKind.EXTERNAL);
        assertThat(graph.nodes()).noneMatch(n -> n.id().contains("secret") || n.name().contains("secret"));
    }

    @Test
    void aDatabaseUrlIsAnEdgeToADatabaseNode() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "spring:\n  datasource:\n    url: jdbc:postgresql://db:5432/app\n"));

        assertThat(TopologyHarness.node(graph, "db-5432").kind()).isEqualTo(NodeKind.DATABASE);
        assertThat(TopologyHarness.edge(graph, "a", "db-5432").protocol()).isEqualTo(Protocol.OTHER);
    }

    @Test
    void gatewayRoutesAreEdgesFromTheGatewayAndAnLbUriNamesTheService() {
        String gateway = TopologyHarness.yaml("edge", """
                spring:
                  cloud:
                    gateway:
                      server:
                        webflux:
                          routes:
                            - id: orders
                              uri: lb://orders
                            - id: pay
                              uri: https://pay:9445
                """);
        ServiceGraph graph = TopologyHarness.graph("edge/pom.xml", TopologyHarness.pom("17"), "edge/src/main/resources/application.yml", gateway,
                "orders/pom.xml", TopologyHarness.pom("17"), "orders/src/main/resources/application.yml", TopologyHarness.yaml("orders", ""));

        assertThat(TopologyHarness.node(graph, "edge").kind()).isEqualTo(NodeKind.GATEWAY);
        assertThat(TopologyHarness.edge(graph, "edge", "orders").protocol()).isEqualTo(Protocol.HTTP);
        assertThat(TopologyHarness.edge(graph, "edge", "pay-9445").tls()).isTrue();
    }

    @Test
    void mutualTlsNeedsTheServerToAskAndTheClientToHaveAnIdentity() {
        String client = TopologyHarness.yaml("a", """
                peer:
                  url: https://b:9444
                spring:
                  ssl:
                    bundle:
                      pem:
                        peer:
                          keystore:
                            certificate: file:/certs/client.crt.pem
                            private-key: file:/certs/client.key.pem
                  http:
                    client:
                      ssl:
                        bundle: peer
                """);
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"), "a/src/main/resources/application.yml", client,
                "b/pom.xml", TopologyHarness.pom("17"), "b/src/main/resources/application.yml", TopologyHarness.yaml("b", SERVER_WITH_MTLS),
                "certs/client.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        ServiceEdge edge = TopologyHarness.edge(graph, "a", "b");
        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).isTrue();
        assertThat(edge.findings()).extracting(f -> f.file().value()).contains("certs/client.crt.pem", "certs/server.crt.pem");
    }

    @Test
    void aHttpClientThatReadsAConfiguredUrlAndAsksForABundleIsMutualTls() {
        String config = TopologyHarness.yaml("a", """
                peer-url: https://b:9444
                spring:
                  ssl:
                    bundle:
                      pem:
                        mtls:
                          keystore:
                            certificate: file:/certs/client.crt.pem
                            private-key: file:/certs/client.key.pem
                """);
        String java = """
                import org.springframework.boot.ssl.SslBundles;
                import org.springframework.web.client.RestClient;

                class PeerClient {
                    private final Props props;
                    PeerClient(Props props, SslBundles bundles) {
                        this.props = props;
                        RestClient.builder().baseUrl(props.peerUrl());
                        bundles.getBundle("mtls");
                    }
                }
                """;
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("25"), "a/src/main/resources/application.yml", config,
                "a/src/main/java/PeerClient.java", java, "b/pom.xml", TopologyHarness.pom("25"),
                "b/src/main/resources/application.yml", TopologyHarness.yaml("b", SERVER_WITH_MTLS),
                "certs/client.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        ServiceEdge edge = TopologyHarness.edge(graph, "a", "b");
        assertThat(edge.mtls()).isTrue();
        assertThat(edge.evidence()).extracting(e -> e.file().value()).contains("a/src/main/java/PeerClient.java", "a/src/main/resources/application.yml");
    }

    @Test
    void feignClientsUseTheUrlOrTheName() {
        String java = """
                import org.springframework.cloud.openfeign.FeignClient;

                @FeignClient(name = "inventory")
                interface InventoryApi { }

                @FeignClient(name = "ignored", url = "https://ledger:9500")
                interface LedgerApi { }

                @FeignClient("${shipping.name}")
                interface ShippingApi { }
                """;
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"), "a/src/main/java/Apis.java", java,
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "shipping:\n  name: shipping-svc\n"));

        assertThat(TopologyHarness.edge(graph, "a", "inventory").protocol()).isEqualTo(Protocol.HTTP);
        assertThat(TopologyHarness.edge(graph, "a", "ledger-9500").tls()).isTrue();
        TopologyHarness.assertNoEdge(graph, "a", "ignored");
        assertThat(TopologyHarness.edge(graph, "a", "shipping-svc").protocol()).isEqualTo(Protocol.HTTP);
    }

    @Test
    void aFileThatIsTestCodeDoesNotStartAnEdge() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("17"),
                "a/src/test/resources/application.yml", TopologyHarness.yaml("a", "peer:\n  url: http://b:1\n"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", ""));

        assertThat(graph.edges()).isEmpty();
    }
}
