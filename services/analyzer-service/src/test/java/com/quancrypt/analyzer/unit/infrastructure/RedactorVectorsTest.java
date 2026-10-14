package com.quancrypt.analyzer.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.infrastructure.redaction.PatternRedactor;
import com.quancrypt.analyzer.infrastructure.redaction.RedactionRules;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/**
 * The shared redaction vectors (contracts/testdata/redaction/vectors.yaml) against the shared rules, through the
 * line-preserving redactor of the snippet endpoint: zero leakage on every positive vector, no change on every negative one,
 * at least one of each per rule (guardrails-security 5), and the service reads exactly the rules of the contract.
 */
class RedactorVectorsTest {

    private static final Path CONTRACTS = Path.of(System.getProperty("quancrypt.contracts.dir"));

    private static RedactionRules contractRules() throws IOException {
        try (InputStream in = Files.newInputStream(CONTRACTS.resolve("redaction-rules.yaml"))) {
            return RedactionRules.parse(in);
        }
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> vectors() throws IOException {
        try (InputStream in = Files.newInputStream(CONTRACTS.resolve("testdata/redaction/vectors.yaml"))) {
            Map<String, Object> root = new Yaml(new SafeConstructor(new LoaderOptions())).load(in);
            return (List<Map<String, Object>>) root.get("vectors");
        }
    }

    private static String redact(PatternRedactor redactor, String text) {
        List<String> lines = Arrays.asList(text.split("\n", -1));
        List<String> redacted = redactor.redactLines(lines);
        assertThat(redacted).hasSameSizeAs(lines);
        return String.join("\n", redacted);
    }

    @TestFactory
    Stream<DynamicTest> everyVectorHolds() throws IOException {
        PatternRedactor redactor = new PatternRedactor(contractRules());
        List<DynamicTest> tests = new ArrayList<>();
        for (Map<String, Object> v : vectors()) {
            String input = (String) v.get("input");
            String rule = (String) v.get("rule");
            tests.add(DynamicTest.dynamicTest((String) v.get("id"), () -> {
                String output = redact(redactor, input);
                if ("positive".equals(v.get("kind"))) {
                    assertThat(output).contains("[REDACTED:" + rule + "]");
                    @SuppressWarnings("unchecked")
                    List<String> secrets = (List<String>) v.get("secrets");
                    assertThat(secrets).isNotEmpty();
                    secrets.forEach(secret -> assertThat(output).doesNotContain(secret));
                } else {
                    assertThat(output).isEqualTo(input);
                }
            }));
        }
        return tests.stream();
    }

    @Test
    void everyRuleHasAPositiveAndANegativeVector() throws IOException {
        RedactionRules rules = contractRules();
        Set<String> ruleIds = new HashSet<>();
        rules.patterns().forEach(r -> ruleIds.add(r.id()));
        ruleIds.add(rules.highEntropy().id());
        for (String id : ruleIds) {
            List<Object> kinds = vectors().stream().filter(v -> id.equals(v.get("rule"))).map(v -> v.get("kind")).toList();
            assertThat(kinds).as(id).contains("positive", "negative");
        }
    }

    /**
     * The worst input for the jwt rule (a run of eyJxxxxx-) takes about three seconds per MiB since its parts are bounded and
     * matched atomically; unbounded it took half an hour (security review P3.3). The limit is a generous bound, not a goal.
     */
    @Test
    void pathologicalInputsAreRedactedQuickly() throws IOException {
        PatternRedactor redactor = new PatternRedactor(contractRules());
        List<String> inputs = List.of("a".repeat(200_000), "a.".repeat(100_000), "x@".repeat(50_000) + "y",
                "-----BEGIN PRIVATE KEY-----".repeat(4_000), "password=\"" + "z".repeat(200_000), "a@b.".repeat(30_000), "eyJxxxxx-".repeat(100_000), "eyJxxxxx.eyJxxxxx-".repeat(50_000));
        for (String input : inputs) {
            // CPU time of this thread: a loaded machine (another build, a reviewer's probes) must not fail the test.
            long started = cpuNanos();
            redactor.redactLines(List.of(input));
            assertThat(Duration.ofNanos(cpuNanos() - started)).as(input.substring(0, 20)).isLessThan(Duration.ofSeconds(10));
        }
    }

    @Test
    void textLongerThanTheLimitIsMaskedLineByLineAndTheLineCountStays() throws IOException {
        RedactionRules rules = contractRules();
        PatternRedactor redactor = new PatternRedactor(rules);
        List<String> lines = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            lines.add("x".repeat(rules.maxInputLength() / 2));
        }

        assertThat(redactor.redactLines(lines)).containsExactly("[REDACTED:max_input_length]", "[REDACTED:max_input_length]",
                "[REDACTED:max_input_length]");
    }

    @Test
    void theServiceReadsTheSameRulesAsTheContract() throws IOException {
        try (InputStream packaged = RedactionRules.class.getClassLoader().getResourceAsStream(RedactionRules.CLASSPATH_LOCATION)) {
            assertThat(packaged).isNotNull();
            assertThat(packaged.readAllBytes()).isEqualTo(Files.readAllBytes(CONTRACTS.resolve("redaction-rules.yaml")));
        }
        assertThat(RedactionRules.fromClasspath().patterns()).isNotEmpty();
    }

    private static long cpuNanos() {
        return java.lang.management.ManagementFactory.getThreadMXBean().getCurrentThreadCpuTime();
    }
}
