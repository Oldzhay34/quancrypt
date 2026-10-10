package com.quancrypt.core.infrastructure.anonymization;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/** The parsed contracts/redaction-rules.yaml (guardrails-security section 5); loading fails fast on any malformed rule. */
public record RedactionRules(String replacement, int maxInputLength, List<PatternRule> patterns, HighEntropyRule highEntropy) {

    public static final String CLASSPATH_LOCATION = "redaction/redaction-rules.yaml";
    public static final String TOO_LONG_RULE = "max_input_length";
    static final int SUPPORTED_VERSION = 1;

    public RedactionRules {
        patterns = List.copyOf(patterns);
        if (!replacement.contains("{rule}")) {
            throw new IllegalArgumentException("replacement must contain {rule}");
        }
        if (maxInputLength < 1) {
            throw new IllegalArgumentException("max_input_length must be positive");
        }
    }

    /** A regular expression rule; valueGroup 0 replaces the whole match, otherwise only that group. */
    public record PatternRule(String id, Pattern pattern, int valueGroup) {
    }

    /** Tokens of tokenPattern at least minLength long with Shannon entropy of at least minBitsPerChar (D-160). */
    public record HighEntropyRule(String id, Pattern tokenPattern, int minLength, double minBitsPerChar) {
    }

    public String marker(String ruleId) {
        return replacement.replace("{rule}", ruleId);
    }

    public static RedactionRules fromClasspath() {
        try (InputStream in = RedactionRules.class.getClassLoader().getResourceAsStream(CLASSPATH_LOCATION)) {
            if (in == null) {
                throw new IllegalStateException("redaction rules are missing from the classpath: " + CLASSPATH_LOCATION);
            }
            return parse(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static RedactionRules parse(InputStream yaml) {
        Map<String, Object> root = new Yaml(new SafeConstructor(new LoaderOptions())).load(yaml);
        if (!Integer.valueOf(SUPPORTED_VERSION).equals(root.get("version"))) {
            throw new IllegalArgumentException("unsupported redaction rules version: " + root.get("version"));
        }
        List<PatternRule> patterns = new ArrayList<>();
        for (Object item : list(root, "rules")) {
            Map<String, Object> rule = map(item, "rule");
            int valueGroup = rule.containsKey("value_group") ? number(rule, "value_group").intValue() : 0;
            Pattern pattern = Pattern.compile(text(rule, "pattern"));
            if (valueGroup < 0 || valueGroup > pattern.matcher("").groupCount()) {
                throw new IllegalArgumentException("value_group out of range in rule " + text(rule, "id"));
            }
            patterns.add(new PatternRule(text(rule, "id"), pattern, valueGroup));
        }
        Map<String, Object> entropy = map(root.get("high_entropy"), "high_entropy");
        HighEntropyRule highEntropy = new HighEntropyRule(text(entropy, "id"), Pattern.compile(text(entropy, "token_pattern")),
                number(entropy, "min_length").intValue(), number(entropy, "min_bits_per_char").doubleValue());
        if (highEntropy.minLength() < 1 || highEntropy.minBitsPerChar() <= 0) {
            throw new IllegalArgumentException("high_entropy thresholds must be positive");
        }
        return new RedactionRules(text(root, "replacement"), number(root, "max_input_length").intValue(), patterns, highEntropy);
    }

    private static List<?> list(Map<String, Object> map, String key) {
        if (map.get(key) instanceof List<?> list) {
            return list;
        }
        throw new IllegalArgumentException(key + " must be a list");
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value, String what) {
        if (value instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        throw new IllegalArgumentException(what + " must be a mapping");
    }

    private static String text(Map<String, Object> map, String key) {
        if (map.get(key) instanceof String s && !s.isBlank()) {
            return s;
        }
        throw new IllegalArgumentException(key + " must be a non-empty string");
    }

    private static Number number(Map<String, Object> map, String key) {
        if (map.get(key) instanceof Number n) {
            return n;
        }
        throw new IllegalArgumentException(key + " must be a number");
    }
}
