package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/** gRPC channels built with ManagedChannelBuilder (GrpcChannelDetector; QBank has none, so unit tests only). */
class GrpcChannelTopologyTest {

    private static ServiceGraph graph(String body) {
        String java = "import io.grpc.ManagedChannelBuilder;\nimport io.grpc.netty.NettyChannelBuilder;\n\nclass Clients {\n    static final String HOST = \"billing\";\n"
                + "    void open() {\n        " + body + "\n    }\n}\n";
        return TopologyHarness.graph("orders/pom.xml", TopologyHarness.pom("17"), "orders/src/main/java/Clients.java", java);
    }

    @Test
    void forAddressWithAPlaintextChannelIsAnUnencryptedGrpcEdge() {
        ServiceGraph graph = graph("ManagedChannelBuilder.forAddress(HOST, 9090).usePlaintext().build();");

        ServiceEdge edge = TopologyHarness.edge(graph, "orders", "billing-9090");
        assertThat(edge.protocol()).isEqualTo(Protocol.GRPC);
        assertThat(edge.tls()).isFalse();
        assertThat(edge.evidence()).hasSize(1);
        assertThat(edge.evidence().get(0).file().value()).isEqualTo("orders/src/main/java/Clients.java");
    }

    @Test
    void transportSecurityInTheChainMakesTheChannelTls() {
        ServiceGraph graph = graph("ManagedChannelBuilder.forAddress(\"ledger\", 443).useTransportSecurity().build();");

        assertThat(TopologyHarness.edge(graph, "orders", "ledger-443").tls()).isTrue();
    }

    @Test
    void aChannelWithNeitherSettingIsReportedWithoutTlsBecauseTheCodeShowsNone() {
        ServiceGraph graph = graph("ManagedChannelBuilder.forAddress(\"ledger\", 443).build();");

        assertThat(TopologyHarness.edge(graph, "orders", "ledger-443").tls()).isFalse();
    }

    @Test
    void forTargetTakesHostAndPortAndTheNettyBuilderIsRecognisedToo() {
        ServiceGraph graph = graph("ManagedChannelBuilder.forTarget(\"dns:///audit:7000\").build(); NettyChannelBuilder.forAddress(\"cards\", 7100).build();");

        assertThat(TopologyHarness.edge(graph, "orders", "audit-7000").protocol()).isEqualTo(Protocol.GRPC);
        assertThat(TopologyHarness.edge(graph, "orders", "cards-7100").protocol()).isEqualTo(Protocol.GRPC);
    }

    @Test
    void anAddressThatIsNotAConstantIsNotGuessed() {
        ServiceGraph graph = graph("String host = System.getenv(\"H\"); ManagedChannelBuilder.forAddress(host, 9090).build();");

        assertThat(graph.edges()).isEmpty();
    }
}
