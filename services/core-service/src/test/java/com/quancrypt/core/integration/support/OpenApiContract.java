package com.quancrypt.core.integration.support;

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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;
import tools.jackson.databind.json.JsonMapper;

/** contracts/openapi/core-service.yaml read for tests: the operations, their security and response schemas (JSON Schema 2020-12 from OpenAPI 3.1). */
public final class OpenApiContract {

    /** One operation of the contract. */
    public record Operation(String id, String method, String path, List<String> securitySchemes, Map<String, Object> responses) {

        public String key() {
            return method + " " + path;
        }
    }

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Path FILE = Path.of(System.getProperty("quancrypt.contracts.dir"), "openapi", "core-service.yaml");

    private final Map<String, Object> document;
    private final List<Operation> operations = new ArrayList<>();

    @SuppressWarnings("unchecked")
    public OpenApiContract() {
        try (InputStream in = Files.newInputStream(FILE)) {
            document = new Yaml(new SafeConstructor(new LoaderOptions())).load(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        Map<String, Object> paths = (Map<String, Object>) document.get("paths");
        for (Map.Entry<String, Object> path : paths.entrySet()) {
            for (Map.Entry<String, Object> op : ((Map<String, Object>) path.getValue()).entrySet()) {
                if (Set.of("get", "post", "put", "delete").contains(op.getKey())) {
                    Map<String, Object> operation = (Map<String, Object>) op.getValue();
                    List<String> schemes = new ArrayList<>();
                    for (Object requirement : (List<Object>) operation.get("security")) {
                        schemes.addAll(((Map<String, Object>) requirement).keySet());
                    }
                    operations.add(new Operation((String) operation.get("operationId"), op.getKey().toUpperCase(), path.getKey(), schemes,
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

    /** The schema a response of the operation declares for the status and media type, if it declares a JSON schema. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> responseSchema(Operation operation, int status, String mediaType) {
        Map<String, Object> response = resolve((Map<String, Object>) operation.responses().get(String.valueOf(status)));
        if (response == null || !response.containsKey("content")) {
            return null;
        }
        Map<String, Object> content = (Map<String, Object>) response.get("content");
        Map<String, Object> media = (Map<String, Object>) content.get(mediaType);
        return media == null ? null : (Map<String, Object>) media.get("schema");
    }

    /** True when the operation declares a response with this status (inline or by $ref to components/responses). */
    public boolean declares(Operation operation, int status) {
        return operation.responses().containsKey(String.valueOf(status));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> resolve(Map<String, Object> response) {
        if (response != null && response.containsKey("$ref")) {
            String ref = (String) response.get("$ref");
            Map<String, Object> node = document;
            for (String part : ref.substring(2).split("/")) {
                node = (Map<String, Object>) node.get(part);
            }
            return node;
        }
        return response;
    }

    /** A validator for a schema of the contract: the schema is the root, the components stay reachable for its $refs. */
    @SuppressWarnings("unchecked")
    public Schema validatorFor(Map<String, Object> schema) {
        Map<String, Object> root = new LinkedHashMap<>(schema);
        root.put("$schema", "https://json-schema.org/draft/2020-12/schema");
        root.put("components", document.get("components"));
        return SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12).getSchema(JSON.writeValueAsString(root), InputFormat.JSON);
    }
}
