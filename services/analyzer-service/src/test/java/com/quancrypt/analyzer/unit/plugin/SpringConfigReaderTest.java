package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Placeholders;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class SpringConfigReaderTest {

    private final SpringConfigReader reader = new SpringConfigReader();
    private final RelativePath file = RelativePath.of("src/main/resources/application.yml");

    @Test
    void yamlIsFlattenedWithLineNumbersAndListIndexes() {
        List<ConfigProperty> properties = reader.yaml(file, """
                server:
                  port: 8443
                  ssl:
                    bundle: demo
                spring:
                  jackson:
                    deserialization:
                      fail-on-unknown-properties: true
                protocols:
                  - TLSv1.3
                  - TLSv1.2
                """);

        assertThat(properties).extracting(ConfigProperty::key).containsExactly("server.port", "server.ssl.bundle",
                "spring.jackson.deserialization.fail-on-unknown-properties", "protocols[0]", "protocols[1]");
        assertThat(properties.get(1).line()).isEqualTo(4);
        assertThat(properties.get(1).value()).isEqualTo("demo");
        assertThat(properties.get(4).value()).isEqualTo("TLSv1.2");
    }

    @Test
    void profileDocumentsKeepTheirProfileName() {
        List<ConfigProperty> properties = reader.yaml(file, """
                server:
                  ssl:
                    bundle: dev-bundle
                ---
                spring:
                  config:
                    activate:
                      on-profile: prod
                server:
                  ssl:
                    bundle: prod-bundle
                """);

        List<ConfigProperty> bundles = properties.stream().filter(p -> p.key().equals("server.ssl.bundle")).toList();
        assertThat(bundles).extracting(ConfigProperty::value).containsExactly("dev-bundle", "prod-bundle");
        assertThat(bundles.get(0).profile()).isEmpty();
        assertThat(bundles.get(1).profile()).contains("prod");
    }

    @Test
    void propertiesFilesHandleSeparatorsCommentsAndContinuationLines() {
        List<ConfigProperty> properties = reader.properties(RelativePath.of("application.properties"), List.of(
                "# comment", "! another comment", "server.ssl.bundle=demo", "spring.application.name: quancrypt",
                "long.value=first \\", "    second", "", "novalue"));

        assertThat(properties).extracting(ConfigProperty::key).containsExactly("server.ssl.bundle", "spring.application.name", "long.value");
        assertThat(properties.get(1).value()).isEqualTo("quancrypt");
        assertThat(properties.get(2).value()).isEqualTo("first second");
        assertThat(properties.get(0).line()).isEqualTo(3);
        assertThat(properties.get(0).profile()).isEqualTo(Optional.empty());
    }

    @Test
    void brokenOrHostileYamlNeverThrowsAndAliasBombsAreStopped() {
        assertThat(reader.yaml(file, "key: [unclosed\n  : ::")).isEmpty();
        StringBuilder bomb = new StringBuilder("a: &a [x, x, x, x, x, x, x, x, x]\n");
        char name = 'b';
        String previous = "a";
        for (int i = 0; i < 12; i++) {
            bomb.append(name).append(": &").append(name).append(" [");
            bomb.append(String.join(", ", java.util.Collections.nCopies(9, "*" + previous))).append("]\n");
            previous = String.valueOf(name);
            name++;
        }
        assertThat(reader.yaml(file, bomb.toString())).hasSizeLessThan(20_001);
    }

    @Test
    void placeholdersResolveAgainstPropertiesAndDefaults() {
        Map<String, String> known = Map.of("qbank.certs-dir", "/certs", "qbank.account-service-url", "https://account:9444");

        assertThat(Placeholders.resolve("${qbank.certs-dir}/ca.crt.pem", k -> Optional.ofNullable(known.get(k)))).isEqualTo("/certs/ca.crt.pem");
        assertThat(Placeholders.resolve("${ACCOUNT_URL:https://localhost:9444}", k -> Optional.empty())).isEqualTo("https://localhost:9444");
        assertThat(Placeholders.resolve("${missing}/x", k -> Optional.empty())).isEqualTo("${missing}/x");
        assertThat(Placeholders.resolve("${qbank.account-service-url}/jwks", k -> Optional.ofNullable(known.get(k))))
                .isEqualTo("https://account:9444/jwks");
        assertThat(Placeholders.resolve("${a:${b:c}}", k -> Optional.empty())).isEqualTo("c");
    }

    @Test
    void aPlaceholderChainThatMultipliesIsLeftAsWritten() {
        Map<String, String> values = Map.of("b", "${c}".repeat(1000), "c", "${d}".repeat(1000), "d", "x".repeat(1000));
        String value = "${b}".repeat(1000);

        String resolved = assertTimeoutPreemptively(Duration.ofSeconds(10),
                () -> Placeholders.resolve(value, key -> Optional.ofNullable(values.get(key))));

        assertThat(resolved.length()).isLessThanOrEqualTo(8192);
    }

    @Test
    void aValueLongerThanTheLimitIsNotResolvedAtAll() {
        String value = "${a}" + "y".repeat(9000);

        assertThat(Placeholders.resolve(value, key -> Optional.of("replaced"))).isEqualTo(value);
    }

    @Test
    void aVeryLongKeyIsSkippedWithEverythingBelowIt() {
        String text = "? " + "k".repeat(5_000) + "\n:\n  a: 1\n  b: 2\nsafe: 1\n";

        assertThat(reader.yaml(file, text)).extracting(ConfigProperty::key).containsExactly("safe");
    }
}
