package com.quancrypt.analyzer.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.DocumentContext;
import com.jayway.jsonpath.JsonPath;
import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.domain.model.Snippet;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.usecase.AnalyzeCryptoService;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

/**
 * The domain code lists and limits are those of the contract (D-17): finding.schema.json, topology.schema.json and
 * analyzer-service.yaml are read from contracts/ and compared with the enums and constants, so they cannot drift apart.
 */
class CodeListContractTest {

    private static DocumentContext finding;
    private static DocumentContext topology;
    private static DocumentContext openapi;

    @BeforeAll
    static void readContracts() throws IOException {
        Path contracts = Path.of(System.getProperty("quancrypt.contracts.dir"));
        finding = JsonPath.parse(Files.readString(contracts.resolve("schemas/finding.schema.json")));
        topology = JsonPath.parse(Files.readString(contracts.resolve("schemas/topology.schema.json")));
        try (InputStream in = Files.newInputStream(contracts.resolve("openapi/analyzer-service.yaml"))) {
            Map<String, Object> spec = new Yaml().load(in);
            openapi = JsonPath.parse(spec);
        }
    }

    private static List<String> names(Enum<?>[] values) {
        return Arrays.stream(values).map(Enum::name).toList();
    }

    private static List<String> list(DocumentContext doc, String path) {
        return doc.read(path);
    }

    @Test
    void findingCodeListsMatchTheDomain() {
        assertThat(list(finding, "$.properties.algorithm_family.enum")).containsExactlyElementsOf(names(AlgorithmFamily.values()));
        assertThat(list(finding, "$.properties.usage_context.enum")).containsExactlyElementsOf(names(UsageContext.values()));
        assertThat(list(finding, "$.properties.location_kind.enum")).containsExactlyElementsOf(names(LocationKind.values()));
        assertThat(list(finding, "$.properties.priority.enum")).containsExactlyElementsOf(names(Priority.values()));
    }

    @Test
    void topologyCodeListsAndLimitsMatchTheDomain() {
        assertThat(list(topology, "$['$defs'].node.properties.kind.enum")).containsExactlyElementsOf(names(NodeKind.values()));
        assertThat(list(topology, "$['$defs'].edge.properties.protocol.enum")).containsExactlyElementsOf(names(Protocol.values()));
        assertThat(list(topology, "$['$defs'].evidence.properties.location_kind.enum")).containsExactlyElementsOf(names(LocationKind.values()));
        assertThat((Integer) topology.read("$.properties.nodes.maxItems")).isEqualTo(ServiceGraph.MAX_NODES);
        assertThat((Integer) topology.read("$.properties.edges.maxItems")).isEqualTo(ServiceGraph.MAX_EDGES);
        assertThat((Integer) topology.read("$['$defs'].node.properties.evidence.maxItems")).isEqualTo(ServiceNode.MAX_EVIDENCE);
        assertThat((Integer) topology.read("$['$defs'].edge.properties.evidence.maxItems")).isEqualTo(ServiceNode.MAX_EVIDENCE);
    }

    @Test
    void openApiCodeListsAndLimitsMatchTheDomain() {
        assertThat(list(openapi, "$.components.schemas.AnalysisResult.properties.project_type.enum"))
                .containsExactlyElementsOf(names(ProjectType.values()));
        assertThat(list(openapi, "$.components.schemas.Plugin.properties.project_types.items.enum"))
                .containsExactlyElementsOf(names(ProjectType.values()));
        assertThat((Integer) openapi.read("$.components.schemas.AnalysisResult.properties.findings.maxItems"))
                .isEqualTo(AnalyzeCryptoService.MAX_FINDINGS);
        assertThat((Integer) openapi.read("$.components.schemas.Snippet.properties.lines.maxItems")).isEqualTo(Snippet.MAX_LINES);
        assertThat((Integer) openapi.read("$.paths['/api/v1/snippets'].get.parameters[4].schema.maximum")).isEqualTo(Snippet.MAX_CONTEXT);
    }
}
