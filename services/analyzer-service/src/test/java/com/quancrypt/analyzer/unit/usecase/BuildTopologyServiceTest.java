package com.quancrypt.analyzer.unit.usecase;

import static com.quancrypt.analyzer.unit.usecase.Fixtures.GRADLE_ROOT;
import static com.quancrypt.analyzer.unit.usecase.Fixtures.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.fake.FakePlugin;
import com.quancrypt.analyzer.port.inbound.BuildTopologyCommand;
import com.quancrypt.analyzer.port.inbound.EdgeView;
import com.quancrypt.analyzer.port.inbound.EvidenceView;
import com.quancrypt.analyzer.port.inbound.NodeView;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.inbound.TopologyView;
import com.quancrypt.analyzer.usecase.BuildTopologyService;
import com.quancrypt.analyzer.usecase.PluginSelector;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class BuildTopologyServiceTest {

    private static final Evidence YAML = new Evidence(RelativePath.of("src/main/resources/application.yml"),
            Optional.of(new LineRange(3, 5)), LocationKind.CONFIG);

    @Test
    void theSupportingPluginsGraphIsMappedToTheView() {
        ServiceGraph graph = new ServiceGraph(
                List.of(new ServiceNode("gw", "gateway", NodeKind.GATEWAY, List.of(YAML)),
                        new ServiceNode("broker", "mosquitto", NodeKind.BROKER, List.of())),
                List.of(new ServiceEdge("gw", "broker", Protocol.MQTT, true, false, List.of(YAML))));
        FakePlugin plugin = new FakePlugin("java", ProjectType.GRADLE).graph(graph);
        BuildTopologyService service = new BuildTopologyService(Fixtures.opener(Fixtures.projects()), new PluginSelector(List.of(plugin)));

        TopologyView view = service.build(new BuildTopologyCommand(GRADLE_ROOT));

        EvidenceView evidence = new EvidenceView("src/main/resources/application.yml", Optional.of(3), Optional.of(5), "CONFIG");
        assertThat(view.nodes()).containsExactly(new NodeView("gw", "gateway", "GATEWAY", List.of(evidence)),
                new NodeView("broker", "mosquitto", "BROKER", List.of()));
        assertThat(view.edges()).containsExactly(new EdgeView("gw", "broker", "MQTT", true, false, List.of(evidence)));
    }

    @Test
    void withoutASupportingPluginTheProjectIsUnsupported() {
        BuildTopologyService service = new BuildTopologyService(Fixtures.opener(Fixtures.projects()),
                new PluginSelector(List.of(new FakePlugin("maven-only", ProjectType.MAVEN))));

        assertProblem(() -> service.build(new BuildTopologyCommand(GRADLE_ROOT)), ProblemCode.UNSUPPORTED_PROJECT);
    }
}
