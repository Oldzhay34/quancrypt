package com.quancrypt.analyzer.unit.cbom;

import com.networknt.schema.Error;
import com.networknt.schema.InputFormat;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

/**
 * The CycloneDX 1.6 JSON schema with the two schemas it points to (SPDX license ids and the JSON signature format), read
 * from src/test/resources/cyclonedx. The files are copied unchanged from the schemas that ship in the
 * cyclonedx-core-java 13.2.0 JAR (D-200), so the version is fixed by the files and not by the library that writes the CBOM.
 */
final class CycloneDxSchema {

    private static final String BASE = "http://cyclonedx.org/schema/";
    private static final Schema BOM = load();

    private CycloneDxSchema() {
    }

    static List<Error> validate(String json) {
        return BOM.validate(json, InputFormat.JSON);
    }

    private static Schema load() {
        Map<String, String> schemas = Map.of(
                BASE + "bom-1.6.schema.json", read("bom-1.6.schema.json"),
                BASE + "spdx.schema.json", read("spdx.schema.json"),
                BASE + "jsf-0.82.schema.json", read("jsf-0.82.schema.json"));
        SchemaRegistry registry = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_7, builder -> builder.schemas(schemas));
        return registry.getSchema(SchemaLocation.of(BASE + "bom-1.6.schema.json"));
    }

    private static String read(String name) {
        try (InputStream in = CycloneDxSchema.class.getResourceAsStream("/cyclonedx/" + name)) {
            if (in == null) {
                throw new IllegalStateException("missing test resource cyclonedx/" + name);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
