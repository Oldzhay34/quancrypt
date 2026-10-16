package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.GroupFamily;
import com.quancrypt.analyzer.domain.model.KeyExchange;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

/**
 * The key exchange of a TLS edge (EdgeCryptoMapper, JdkTlsDefaults; D-208, D-210, D-213): nothing is measured, so what the Java
 * version offers by default is an inference ({@code inferred=true}, confidence below 1) and groups the code or the configuration
 * name are not.
 */
class KeyExchangeInferenceTest {

    private static final String HTTPS = "peer:\n  url: https://b:8443\n";

    private static Optional<KeyExchange> exchangeOf(String javaVersion, String clientConfig, String... extraFiles) {
        String[] files = new String[6 + extraFiles.length];
        files[0] = "a/pom.xml";
        files[1] = javaVersion == null ? "<project/>" : TopologyHarness.pom(javaVersion);
        files[2] = "a/src/main/resources/application.yml";
        files[3] = TopologyHarness.yaml("a", clientConfig);
        files[4] = "b/pom.xml";
        files[5] = javaVersion == null ? "<project/>" : TopologyHarness.pom("17");
        System.arraycopy(extraFiles, 0, files, 6, extraFiles.length);
        ServiceGraph graph = TopologyHarness.graph(files);
        ServiceEdge edge = TopologyHarness.edge(graph, "a", "b");
        return edge.keyExchange();
    }

    @Test
    void jdk25OffersTheClassicalGroupsOfItsDefaultListAndTheConfidenceIsLowest() {
        KeyExchange exchange = exchangeOf("25", HTTPS).orElseThrow();

        assertThat(exchange.groupFamily()).isEqualTo(GroupFamily.CLASSICAL);
        assertThat(exchange.inferred()).isTrue();
        assertThat(exchange.confidence()).isEqualTo(0.5);
        assertThat(exchange.groups()).startsWith("x25519", "secp256r1").doesNotContain("X25519MLKEM768");
    }

    @ParameterizedTest
    @CsvSource({"17,CLASSICAL", "21,CLASSICAL", "24,CLASSICAL", "26,CLASSICAL", "27,HYBRID", "28,HYBRID"})
    void theFamilyFollowsTheJavaVersion(String version, GroupFamily family) {
        KeyExchange exchange = exchangeOf(version, HTTPS).orElseThrow();

        assertThat(exchange.groupFamily()).isEqualTo(family);
        assertThat(exchange.inferred()).isTrue();
        assertThat(exchange.confidence()).isLessThan(1.0);
    }

    @Test
    void jdk27PutsTheHybridGroupFirstAsJep527Says() {
        KeyExchange exchange = exchangeOf("27", HTTPS).orElseThrow();

        assertThat(exchange.groups()).startsWith("X25519MLKEM768", "x25519");
    }

    @Test
    void groupsOtherThan25AreNotListedBecauseTheirOrderWasNotChecked() {
        assertThat(exchangeOf("17", HTTPS).orElseThrow().groups()).isEmpty();
    }

    @Test
    void anUnknownJavaVersionGivesNoKeyExchange() {
        assertThat(exchangeOf(null, HTTPS)).isEmpty();
    }

    @Test
    void groupsNamedInConfigurationAreNotAnInference() {
        KeyExchange exchange = exchangeOf("25", HTTPS + "jdk.tls.namedGroups: X25519MLKEM768, x25519\n").orElseThrow();

        assertThat(exchange.inferred()).isFalse();
        assertThat(exchange.groupFamily()).isEqualTo(GroupFamily.HYBRID);
        assertThat(exchange.groups()).containsExactly("X25519MLKEM768", "x25519");
        assertThat(exchange.confidence()).as("a hybrid group named for a JDK that has none may be ignored").isEqualTo(0.5);
    }

    @Test
    void aNamedHybridGroupOnJdk27IsTrustedMore() {
        KeyExchange exchange = exchangeOf("27", HTTPS + "jdk.tls.namedGroups: X25519MLKEM768\n").orElseThrow();

        assertThat(exchange.confidence()).isEqualTo(0.9);
    }

    @Test
    void releasesAfterJdk27HaveNoGroupsAndTheLowestConfidence() {
        KeyExchange exchange = exchangeOf("28", HTTPS).orElseThrow();

        assertThat(exchange.groupFamily()).isEqualTo(GroupFamily.HYBRID);
        assertThat(exchange.groups()).isEmpty();
        assertThat(exchange.confidence()).isEqualTo(0.4);
    }

    @Test
    void groupsSetWithASystemPropertyInCodeAreNotAnInferenceEither() {
        String java = "class Boot {\n    static void init() {\n        System.setProperty(\"jdk.tls.namedGroups\", \"secp256r1\");\n    }\n}\n";
        KeyExchange exchange = exchangeOf("25", HTTPS, "a/src/main/java/Boot.java", java).orElseThrow();

        assertThat(exchange.inferred()).isFalse();
        assertThat(exchange.groupFamily()).isEqualTo(GroupFamily.CLASSICAL);
        assertThat(exchange.groups()).containsExactly("secp256r1");
    }

    @Test
    void anEdgeWithoutTlsHasNoKeyExchange() {
        ServiceGraph graph = TopologyHarness.graph("a/pom.xml", TopologyHarness.pom("25"),
                "a/src/main/resources/application.yml", TopologyHarness.yaml("a", "peer:\n  url: http://b:8080\n"));

        assertThat(TopologyHarness.edge(graph, "a", "b-8080").keyExchange()).isEmpty();
    }

    @Test
    void aKeyExchangeThatIsInferredCannotClaimCertainty() {
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> new KeyExchange(GroupFamily.CLASSICAL, java.util.List.of(), true, 1.0))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
