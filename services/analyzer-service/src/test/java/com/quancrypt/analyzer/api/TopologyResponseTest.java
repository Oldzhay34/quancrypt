package com.quancrypt.analyzer.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.api.dto.TopologyResponse;
import com.quancrypt.analyzer.facade.dto.TopologyDto;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

/** The topology body: snake_case like the contract, `key_exchange` only when there is one, evidence lines written even when null. */
class TopologyResponseTest {

    private static final JsonMapper JSON = JsonMapper.builder().propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE).build();

    private static TopologyDto.EdgeDto edge(TopologyDto.KeyExchangeDto exchange) {
        return new TopologyDto.EdgeDto("a", "b", "HTTP", true, false, List.of(new TopologyDto.EvidenceDto("x.yml", null, null, "CONFIG")),
                List.of(new TopologyDto.FindingRefDto("x.yml", "sym", "RSA", "TLS_KEY_EXCHANGE", null)), exchange);
    }

    @Test
    void anEdgeWithoutKeyExchangeLeavesTheFieldOutAndKeepsNullLines() {
        JsonNode edge = JSON.valueToTree(TopologyResponse.of(new TopologyDto(List.of(), List.of(edge(null))))).get("edges").get(0);

        assertThat(edge.has("key_exchange")).isFalse();
        assertThat(edge.get("evidence").get(0).has("line_start")).isTrue();
        assertThat(edge.get("evidence").get(0).get("line_start").isNull()).isTrue();
        assertThat(edge.get("findings").get(0).get("algorithm_family").asString()).isEqualTo("RSA");
        assertThat(edge.get("findings").get(0).get("line_start").isNull()).isTrue();
    }

    @Test
    void anEdgeWithKeyExchangeWritesItInSnakeCase() {
        var exchange = new TopologyDto.KeyExchangeDto("CLASSICAL", List.of("x25519"), true, 0.5);
        JsonNode written = JSON.valueToTree(TopologyResponse.of(new TopologyDto(List.of(), List.of(edge(exchange))))).get("edges").get(0)
                .get("key_exchange");

        assertThat(written.get("group_family").asString()).isEqualTo("CLASSICAL");
        assertThat(written.get("groups").get(0).asString()).isEqualTo("x25519");
        assertThat(written.get("inferred").asBoolean()).isTrue();
        assertThat(written.get("confidence").asDouble()).isEqualTo(0.5);
    }
}
