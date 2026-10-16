package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/** Kafka and RabbitMQ settings become broker edges (MessagingConfigDetector; QBank has neither, D-206 era unit tests only). */
class MessagingConfigTopologyTest {

    private static ServiceGraph graph(String config) {
        return TopologyHarness.graph("orders/pom.xml", TopologyHarness.pom("17"),
                "orders/src/main/resources/application.yml", TopologyHarness.yaml("orders", config));
    }

    @Test
    void kafkaBootstrapServersAreEdgesToBrokerNodes() {
        ServiceGraph graph = graph("  kafka:\n    bootstrap-servers: kafka-1:9092,kafka-2:9092\n");

        ServiceEdge first = TopologyHarness.edge(graph, "orders", "kafka-1-9092");
        assertThat(first.protocol()).isEqualTo(Protocol.KAFKA);
        assertThat(first.tls()).isFalse();
        assertThat(TopologyHarness.node(graph, "kafka-1-9092").kind()).isEqualTo(NodeKind.BROKER);
        assertThat(TopologyHarness.edge(graph, "orders", "kafka-2-9092").protocol()).isEqualTo(Protocol.KAFKA);
    }

    @Test
    void kafkaSslSettingsMakeTheEdgeTls() {
        ServiceGraph graph = graph("  kafka:\n    bootstrap-servers: kafka:9093\n    ssl:\n      bundle: kafkaclient\n");

        assertThat(TopologyHarness.edge(graph, "orders", "kafka-9093").tls()).isTrue();
    }

    @Test
    void rabbitMqHostAndPortAreAnAmqpEdge() {
        ServiceGraph graph = graph("  rabbitmq:\n    host: rabbit\n    port: 5671\n    ssl:\n      enabled: true\n");

        ServiceEdge edge = TopologyHarness.edge(graph, "orders", "rabbit-5671");
        assertThat(edge.protocol()).isEqualTo(Protocol.AMQP);
        assertThat(edge.tls()).isTrue();
        assertThat(TopologyHarness.node(graph, "rabbit-5671").kind()).isEqualTo(NodeKind.BROKER);
    }

    @Test
    void rabbitMqAddressesAreEdgesAndPlainByDefault() {
        ServiceGraph graph = graph("  rabbitmq:\n    addresses: mq1:5672,mq2:5672\n");

        assertThat(TopologyHarness.edge(graph, "orders", "mq1-5672").tls()).isFalse();
        assertThat(TopologyHarness.edge(graph, "orders", "mq2-5672").protocol()).isEqualTo(Protocol.AMQP);
    }

    @Test
    void aProjectWithoutBrokerSettingsHasNoBrokerEdge() {
        ServiceGraph graph = graph("server:\n  port: 8080\n");

        assertThat(graph.edges()).isEmpty();
    }
}
