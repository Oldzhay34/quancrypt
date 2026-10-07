package com.quancrypt.qbank.payment.support;

import com.networknt.schema.Error;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import tools.jackson.dataformat.yaml.YAMLMapper;

/** Reads an OpenAPI 3.1 contract and validates JSON against the schemas in its components. */
public final class ContractSchemas {

    private static final Set<String> HTTP_METHODS = Set.of("get", "post", "put", "delete", "patch");

    private final JsonNode document;
    private final ObjectMapper json = new ObjectMapper();
    private final SchemaRegistry registry = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12);

    private ContractSchemas(JsonNode document) {
        this.document = document;
    }

    public static ContractSchemas load(Path openApiFile) {
        try {
            return new ContractSchemas(YAMLMapper.builder().build().readTree(Files.readString(openApiFile)));
        } catch (IOException e) {
            throw new IllegalStateException("cannot read contract " + openApiFile, e);
        }
    }

    /** All operations of the contract as "METHOD /path". */
    public Set<String> operations() {
        Set<String> operations = new TreeSet<>();
        document.get("paths").properties().forEach(path -> path.getValue().propertyNames().stream()
                .filter(HTTP_METHODS::contains)
                .forEach(method -> operations.add(method.toUpperCase(Locale.ROOT) + " " + path.getKey())));
        return operations;
    }

    /** The response status codes the contract documents for an operation. */
    public Set<String> responseCodes(String method, String path) {
        Set<String> codes = new TreeSet<>();
        document.get("paths").get(path).get(method.toLowerCase(Locale.ROOT)).get("responses")
                .propertyNames().forEach(codes::add);
        return codes;
    }

    /** Validation errors of the JSON text against components.schemas.{schemaName}; empty means valid. */
    public List<String> validate(String schemaName, String jsonText) {
        ObjectNode wrapper = json.createObjectNode();
        wrapper.put("$schema", "https://json-schema.org/draft/2020-12/schema");
        wrapper.put("$ref", "#/components/schemas/" + schemaName);
        wrapper.set("components", document.get("components"));
        Schema schema = registry.getSchema(wrapper);
        List<Error> errors = schema.validate(json.readTree(jsonText));
        return errors.stream().map(Error::getMessage).toList();
    }
}
