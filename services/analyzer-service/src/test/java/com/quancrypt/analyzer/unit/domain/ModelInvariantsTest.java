package com.quancrypt.analyzer.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.AnalysisStats;
import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.PluginInfo;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.domain.model.ServiceNode;
import com.quancrypt.analyzer.domain.model.Snippet;
import com.quancrypt.analyzer.domain.model.SnippetLine;
import com.quancrypt.analyzer.fake.Usages;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ModelInvariantsTest {

    private static final Evidence CONFIG = new Evidence(RelativePath.of("application.yml"), Optional.of(new LineRange(1, 2)), LocationKind.CONFIG);

    private static ServiceNode node(String id) {
        return new ServiceNode(id, id, NodeKind.SERVICE, List.of(CONFIG));
    }

    @Test
    void theCodeListsAreThoseOfCryptoDomainAndTheDecisions() {
        assertThat(AlgorithmFamily.values()).hasSize(21);
        assertThat(NodeKind.values()).extracting(Enum::name)
                .containsExactly("SERVICE", "GATEWAY", "BROKER", "DEVICE", "DATABASE", "EXTERNAL");
        assertThat(Protocol.values()).extracting(Enum::name).containsExactly("HTTP", "GRPC", "MQTT", "AMQP", "KAFKA", "OTHER");
    }

    @Test
    void aCryptoUsageKnowsWhetherItIsTestCode() {
        assertThat(Usages.rsaEncryption("src/test/java/T.java", LocationKind.TEST_CODE).inTestCode()).isTrue();
        assertThat(Usages.rsaEncryption("src/main/java/A.java", LocationKind.CODE).inTestCode()).isFalse();
    }

    @Test
    void rawTokensHaveNoWhitespaceAndKeySizesArePositive() {
        assertThatThrownBy(() -> new CryptoAlgorithm(AlgorithmFamily.AES, "AES", Optional.of("C B C"), Optional.empty(),
                Optional.empty(), Optional.empty())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new CryptoAlgorithm(AlgorithmFamily.AES, "AES", Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.of(0))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new CryptoAlgorithm(AlgorithmFamily.AES, "", Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.empty())).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void confidenceIsBetweenZeroAndOne() {
        var usage = Usages.rsaEncryption("A.java", LocationKind.CODE);
        assertThatThrownBy(() -> new com.quancrypt.analyzer.domain.model.CryptoUsage(usage.evidence(), usage.symbol(), usage.algorithm(),
                usage.usageContext(), usage.priority(), usage.library(), 1.01, usage.detectorId())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new com.quancrypt.analyzer.domain.model.CryptoUsage(usage.evidence(), usage.symbol(), usage.algorithm(),
                usage.usageContext(), usage.priority(), usage.library(), Double.NaN, usage.detectorId())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new com.quancrypt.analyzer.domain.model.CryptoUsage(usage.evidence(), usage.symbol(), usage.algorithm(),
                usage.usageContext(), usage.priority(), usage.library(), 0.5, "Bad Id")).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void aGraphHasUniqueNodesAndEdgesBetweenThem() {
        ServiceEdge edge = new ServiceEdge("a", "b", Protocol.HTTP, true, true, List.of(CONFIG));
        assertThat(new ServiceGraph(List.of(node("a"), node("b")), List.of(edge)).edges()).hasSize(1);
        assertThatThrownBy(() -> new ServiceGraph(List.of(node("a"), node("a")), List.of())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ServiceGraph(List.of(node("a")), List.of(edge))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ServiceGraph(Collections.nCopies(201, node("a")), List.of())).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void mtlsImpliesTls() {
        assertThatThrownBy(() -> new ServiceEdge("a", "b", Protocol.MQTT, false, true, List.of())).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void nodeIdsFollowTheSchemaPattern() {
        assertThatThrownBy(() -> new ServiceNode("a b", "a", NodeKind.SERVICE, List.of())).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void smallValueObjectsCheckTheirRanges() {
        assertThatThrownBy(() -> new LineRange(0, 1)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new LineRange(5, 4)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AnalysisStats(-1, 0, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Cbom("one", "{}")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new SnippetLine(0, "x")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Snippet(RelativePath.of("a"), Collections.nCopies(22, new SnippetLine(1, "x"))))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RuntimeInfo(Optional.of("25 LTS"), Optional.empty())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new PluginInfo("java", "Java", "1.0.0", Set.of())).isInstanceOf(IllegalArgumentException.class);
        assertThat(new PluginInfo("java", "Java", "1.0.0", Set.of(ProjectType.MAVEN)).projectTypes()).containsExactly(ProjectType.MAVEN);
    }
}
