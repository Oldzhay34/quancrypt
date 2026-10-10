package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.NodeKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.Topology;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** TopologyReader and TopologyWriter. */
public abstract class TopologyPortsContract extends PortContract {

    private Topology topology(Tree tree, Finding finding) {
        ServiceNode gateway = new ServiceNode(ids.next(), "gateway", NodeKind.GATEWAY);
        ServiceNode account = new ServiceNode(ids.next(), "account", NodeKind.SERVICE);
        ServiceLink link = new ServiceLink(ids.next(), gateway.id(), account.id(), Protocol.HTTP, true, true,
                List.of(new CallSite(tree.file().id(), 3, 4)), Set.of(finding.id()));
        return new Topology(ids.next(), tree.scan().id(), at(3), List.of(gateway, account), List.of(link));
    }

    @Test
    void topologyRoundTripsWithNodesLinksCallSitesAndFindings() {
        Tree tree = tree();
        Finding finding = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        ports.findingWriter().insertIgnoringDuplicates(List.of(finding));
        Topology topology = topology(tree, finding);

        assertThat(ports.topologyReader().exists(tree.scan().id())).isFalse();
        ports.topologyWriter().insert(topology);

        Topology stored = ports.topologyReader().find(tree.scan().id()).orElseThrow();
        assertThat(ports.topologyReader().exists(tree.scan().id())).isTrue();
        assertThat(stored.id()).isEqualTo(topology.id());
        assertThat(stored.recordedAt()).isEqualTo(topology.recordedAt());
        assertThat(stored.nodes()).containsExactlyInAnyOrderElementsOf(topology.nodes());
        assertThat(stored.links()).containsExactlyInAnyOrderElementsOf(topology.links());
    }

    @Test
    void deleteByScanRemovesTheTopology() {
        Tree tree = tree();
        Finding finding = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        ports.findingWriter().insertIgnoringDuplicates(List.of(finding));
        ports.topologyWriter().insert(topology(tree, finding));

        ports.topologyWriter().deleteByScan(tree.scan().id());

        assertThat(ports.topologyReader().find(tree.scan().id())).isEmpty();
        ports.topologyWriter().insert(topology(tree, finding));
        assertThat(ports.topologyReader().exists(tree.scan().id())).isTrue();
    }
}
