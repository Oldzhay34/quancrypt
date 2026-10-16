package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import org.junit.jupiter.api.Test;

/** The basic Kubernetes manifest reader (D-206): workloads, services, ingress and environment URLs; unit tests only, QBank has no manifests. */
class KubernetesTopologyTest {

    private static final String MANIFEST = """
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: orders
            spec:
              selector:
                matchLabels:
                  app: orders
              template:
                metadata:
                  labels:
                    app: orders
                spec:
                  containers:
                    - name: orders
                      image: example/orders:1
                      ports:
                        - containerPort: 8080
                      env:
                        - name: BILLING_URL
                          value: http://billing-svc:8080
                        - name: MODE
                          value: fast
            ---
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: billing
            spec:
              template:
                metadata:
                  labels:
                    app: billing
                spec:
                  containers:
                    - name: billing
                      image: example/billing:1
            ---
            apiVersion: v1
            kind: Service
            metadata:
              name: billing-svc
            spec:
              selector:
                app: billing
              ports:
                - port: 8080
            ---
            apiVersion: networking.k8s.io/v1
            kind: Ingress
            metadata:
              name: public
            spec:
              tls:
                - hosts: [shop.example.com]
              rules:
                - host: shop.example.com
                  http:
                    paths:
                      - path: /
                        backend:
                          service:
                            name: orders
                            port:
                              number: 8080
            """;

    private static ServiceGraph graph() {
        return TopologyHarness.graph("k8s/app.yaml", MANIFEST);
    }

    @Test
    void workloadsAreNodesAndAServiceIsAnotherNameOfTheWorkloadItSelects() {
        ServiceGraph graph = graph();

        assertThat(graph.nodes()).extracting(n -> n.id()).containsExactly("billing", "external-client", "orders");
        assertThat(TopologyHarness.node(graph, "orders").kind()).isEqualTo(NodeKind.SERVICE);
    }

    @Test
    void anEnvironmentUrlToAServiceIsAConnectionFromTheWorkloadToItsWorkload() {
        ServiceEdge edge = TopologyHarness.edge(graph(), "orders", "billing");

        assertThat(edge.protocol()).isEqualTo(Protocol.HTTP);
        assertThat(edge.tls()).isFalse();
        assertThat(edge.evidence().get(0).file().value()).isEqualTo("k8s/app.yaml");
    }

    @Test
    void anIngressWithTlsHostsIsAnEncryptedConnectionFromOutside() {
        ServiceEdge edge = TopologyHarness.edge(graph(), "external-client", "orders");

        assertThat(edge.tls()).isTrue();
        assertThat(edge.mtls()).isFalse();
    }

    @Test
    void aYamlFileOutsideAKubernetesDirectoryIsNotRead() {
        ServiceGraph graph = TopologyHarness.graph("docs/app.yaml", MANIFEST);

        assertThat(graph.nodes()).isEmpty();
    }

    @Test
    void anInvalidManifestIsSkippedWithoutFailing() {
        ServiceGraph graph = TopologyHarness.graph("k8s/broken.yaml", "kind: [unclosed\n  - : :\n");

        assertThat(graph.nodes()).isEmpty();
    }
}
