package com.quancrypt.analyzer.integration.support;

import com.networknt.schema.Error;
import com.networknt.schema.InputFormat;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * contracts/openapi/analyzer-service.yaml read for tests: the operations and their response schemas (JSON Schema 2020-12
 * from OpenAPI 3.1). A response schema that points into contracts/schemas ({@code $ref: ../schemas/NAME}) is validated
 * with that file as its own schema, because the files carry their own {@code $defs}: the contract schema is checked with the
 * reference left open, and the referenced part (the findings, the topology) is checked against the file.
 */
public final class OpenApiContract {

    /** One operation of the contract. */
    public record Operation(String id, String method, String path, Map<String, Object> responses) {

        public String key() {
            return method + " " + path;
        }
    }

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Path CONTRACTS = Path.of(System.getProperty("quancrypt.contracts.dir"));
    private static final String EXTERNAL_PREFIX = "../schemas/";

    private final Map<String, Object> document;
    private final List<Operation> operations = new ArrayList<>();
    private final Map<String, Schema> external = new HashMap<>();

    @SuppressWarnings("unchecked")
    public OpenApiContract() {
        try (InputStream in = Files.newInputStream(CONTRACTS.resolve("openapi/analyzer-service.yaml"))) {
            document = new Yaml(new SafeConstructor(new LoaderOptions())).load(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        Map<String, Object> paths = (Map<String, Object>) document.get("paths");
        for (Map.Entry<String, Object> path : paths.entrySet()) {
            for (Map.Entry<String, Object> op : ((Map<String, Object>) path.getValue()).entrySet()) {
                if (Set.of("get", "post", "put", "delete").contains(op.getKey())) {
                    Map<String, Object> operation = (Map<String, Object>) op.getValue();
                    operations.add(new Operation((String) operation.get("operationId"), op.getKey().toUpperCase(), path.getKey(),
                            (Map<String, Object>) operation.get("responses")));
                }
            }
        }
    }

    public List<Operation> operations() {
        return List.copyOf(operations);
    }

    public Set<String> operationKeys() {
        Set<String> keys = new TreeSet<>();
        operations.forEach(o -> keys.add(o.key()));
        return keys;
    }

    public Operation operation(String id) {
        return operations.stream().filter(o -> o.id().equals(id)).findFirst().orElseThrow();
    }

    /** True when the operation declares a response with this status (inline or by $ref to components/responses). */
    public boolean declares(Operation operation, int status) {
        return operation.responses().containsKey(String.valueOf(status));
    }

    /** The contract's error for a status: whether the operation declares a body with this media type for it. */
    @SuppressWarnings("unchecked")
    public boolean declaresBody(Operation operation, int status, String mediaType) {
        return responseSchema(operation, status, mediaType) != null;
    }

    /** The errors of a response body against the schema the operation declares for the status and media type. */
    @SuppressWarnings("unchecked")
    public List<Error> validate(Operation operation, int status, String mediaType, String body) {
        Map<String, Object> declared = responseSchema(operation, status, mediaType);
        List<Error> errors = new ArrayList<>();
        if (declared.get("$ref") instanceof String ref && ref.startsWith(EXTERNAL_PREFIX)) {
            errors.addAll(externalSchema(ref.substring(EXTERNAL_PREFIX.length())).validate(body, InputFormat.JSON));
            return errors;
        }
        errors.addAll(validatorFor(declared).validate(body, InputFormat.JSON));
        JsonNode root = JSON.readTree(body);
        // Where the contract schema points at a file in contracts/schemas, that part is validated against the file.
        Map<String, Object> properties = (Map<String, Object>) resolveRef(declared).get("properties");
        if (properties != null) {
            for (Map.Entry<String, Object> property : properties.entrySet()) {
                Map<String, Object> schema = (Map<String, Object>) property.getValue();
                Map<String, Object> items = schema.get("items") instanceof Map<?, ?> m ? (Map<String, Object>) m : null;
                if (items != null && items.get("$ref") instanceof String ref && ref.startsWith(EXTERNAL_PREFIX) && root.has(property.getKey())) {
                    Schema file = externalSchema(ref.substring(EXTERNAL_PREFIX.length()));
                    for (JsonNode item : root.get(property.getKey())) {
                        errors.addAll(file.validate(JSON.writeValueAsString(item), InputFormat.JSON));
                    }
                }
            }
        }
        return errors;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> responseSchema(Operation operation, int status, String mediaType) {
        Map<String, Object> response = resolve((Map<String, Object>) operation.responses().get(String.valueOf(status)));
        if (response == null || !response.containsKey("content")) {
            return null;
        }
        Map<String, Object> media = (Map<String, Object>) ((Map<String, Object>) response.get("content")).get(mediaType);
        return media == null ? null : (Map<String, Object>) media.get("schema");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> resolve(Map<String, Object> node) {
        return node != null && node.containsKey("$ref") ? lookup((String) node.get("$ref")) : node;
    }

    private Map<String, Object> resolveRef(Map<String, Object> schema) {
        return schema.get("$ref") instanceof String ref && ref.startsWith("#/") ? lookup(ref) : schema;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> lookup(String ref) {
        Map<String, Object> node = document;
        for (String part : ref.substring(2).split("/")) {
            node = (Map<String, Object>) node.get(part);
        }
        return node;
    }

    private Schema externalSchema(String name) {
        return external.computeIfAbsent(name, n -> {
            try {
                return SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12)
                        .getSchema(Files.readString(CONTRACTS.resolve("schemas").resolve(n)), InputFormat.JSON);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        });
    }

    /** A validator for a schema of the contract: the schema is the root, the components stay reachable for its $refs. */
    private Schema validatorFor(Map<String, Object> schema) {
        Map<String, Object> root = new LinkedHashMap<>(openedUp(schema));
        root.put("$schema", "https://json-schema.org/draft/2020-12/schema");
        root.put("components", openedUp(document.get("components")));
        return SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12).getSchema(JSON.writeValueAsString(root), InputFormat.JSON);
    }

    /** A copy of the node in which every reference to a file of contracts/schemas is replaced by the open schema. */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> openedUp(Object node) {
        return (Map<String, Object>) open(node);
    }

    @SuppressWarnings("unchecked")
    private static Object open(Object node) {
        if (node instanceof Map<?, ?> map) {
            if (map.get("$ref") instanceof String ref && ref.startsWith(EXTERNAL_PREFIX)) {
                return new LinkedHashMap<String, Object>();
            }
            Map<String, Object> copy = new LinkedHashMap<>();
            ((Map<String, Object>) map).forEach((k, v) -> copy.put(k, open(v)));
            return copy;
        }
        if (node instanceof List<?> list) {
            return list.stream().map(OpenApiContract::open).toList();
        }
        return node;
    }
}
