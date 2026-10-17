package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.event.DomainEvent;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Every domain event payload against its JSON Schema in contracts/schemas/events (D-17, D-142). No schema validator is
 * a dependency (D-158), so this test checks the keywords the event schemas use: type, enum, pattern, required,
 * properties, additionalProperties, propertyNames, items, local $ref and oneOf/anyOf.
 */
class EventSchemaContractTest {

    private static final Path EVENTS = Path.of(System.getProperty("quancrypt.contracts.dir"), "schemas", "events");
    private static final JsonMapper JSON = JsonMapper.builder().build();

    /**
     * Events produced by agent-service (D-232): their schemas live in the shared catalog (D-17) but core never emits them,
     * so there is no core sample to validate; the test asserts that core really does not produce them.
     */
    private static final Set<String> AGENT_PRODUCED = Set.of("scope_decision");

    @TestFactory
    Stream<DynamicTest> everyPayloadMatchesItsSchema() {
        List<DynamicTest> tests = new ArrayList<>();
        int n = 0;
        for (DomainEvent event : SampleEvents.all()) {
            tests.add(DynamicTest.dynamicTest(event.type().code() + "#" + n++, () -> {
                JsonNode root = JSON.readTree(Files.readString(EVENTS.resolve(event.type().code() + ".json")));
                List<String> errors = new ArrayList<>();
                check(root, root.path("properties").path("payload"), JSON.valueToTree(event.payload()), "payload", errors);
                assertThat(errors).as(event.toString()).isEmpty();
            }));
        }
        return tests.stream();
    }

    @TestFactory
    Stream<DynamicTest> everySchemaHasASampleEvent() throws IOException {
        List<String> sampled = SampleEvents.all().stream().map(e -> e.type().code()).distinct().toList();
        try (Stream<Path> files = Files.list(EVENTS)) {
            return files.map(p -> EVENTS.relativize(p).toString().replace(".json", ""))
                    .map(type -> DynamicTest.dynamicTest(type, () -> {
                        if (AGENT_PRODUCED.contains(type)) {
                            assertThat(sampled).doesNotContain(type);
                        } else {
                            assertThat(sampled).contains(type);
                        }
                    }))
                    .toList().stream();
        }
    }

    private static void check(JsonNode root, JsonNode schema, JsonNode value, String path, List<String> errors) {
        if (schema.has("$ref")) {
            String ref = schema.get("$ref").asString();
            check(root, root.at(ref.substring(1)), value, path, errors);
            return;
        }
        for (String keyword : new String[] {"oneOf", "anyOf"}) {
            if (schema.has(keyword)) {
                boolean any = false;
                for (JsonNode branch : schema.get(keyword)) {
                    List<String> branchErrors = new ArrayList<>();
                    check(root, branch, value, path, branchErrors);
                    any |= branchErrors.isEmpty();
                }
                if (!any) {
                    errors.add(path + ": matches no branch of " + keyword);
                }
                return;
            }
        }
        if (schema.has("type") && !typeMatches(schema.get("type"), value)) {
            errors.add(path + ": type " + value.getNodeType() + " is not " + schema.get("type"));
            return;
        }
        if (schema.has("enum") && !contains(schema.get("enum"), value)) {
            errors.add(path + ": " + value + " is not in the enum");
        }
        if (schema.has("pattern") && value.isString() && !Pattern.compile(schema.get("pattern").asString()).matcher(value.asString()).find()) {
            errors.add(path + ": " + value + " does not match the pattern");
        }
        if (value.isObject()) {
            checkObject(root, schema, value, path, errors);
        }
        if (value.isArray() && schema.has("items")) {
            int i = 0;
            for (JsonNode item : value) {
                check(root, schema.get("items"), item, path + "[" + i++ + "]", errors);
            }
        }
    }

    private static void checkObject(JsonNode root, JsonNode schema, JsonNode value, String path, List<String> errors) {
        for (JsonNode required : schema.path("required")) {
            if (!value.has(required.asString())) {
                errors.add(path + ": missing required " + required.asString());
            }
        }
        for (Map.Entry<String, JsonNode> field : value.properties()) {
            String name = field.getKey();
            if (schema.has("propertyNames")) {
                check(root, schema.get("propertyNames"), JSON.valueToTree(name), path + " key " + name, errors);
            }
            JsonNode property = schema.path("properties").path(name);
            if (!property.isMissingNode()) {
                check(root, property, field.getValue(), path + "." + name, errors);
            } else if (schema.path("additionalProperties").isObject()) {
                check(root, schema.get("additionalProperties"), field.getValue(), path + "." + name, errors);
            } else if (schema.path("additionalProperties").isBoolean() && !schema.get("additionalProperties").asBoolean()) {
                errors.add(path + ": property " + name + " is not allowed");
            }
        }
    }

    private static boolean typeMatches(JsonNode type, JsonNode value) {
        if (type.isArray()) {
            for (JsonNode t : type) {
                if (typeMatches(t, value)) {
                    return true;
                }
            }
            return false;
        }
        return switch (type.asString()) {
            case "string" -> value.isString();
            case "integer" -> value.isIntegralNumber();
            case "number" -> value.isNumber();
            case "boolean" -> value.isBoolean();
            case "null" -> value.isNull();
            case "object" -> value.isObject();
            case "array" -> value.isArray();
            default -> false;
        };
    }

    private static boolean contains(JsonNode values, JsonNode value) {
        for (JsonNode v : values) {
            if (v.equals(value)) {
                return true;
            }
        }
        return false;
    }
}
