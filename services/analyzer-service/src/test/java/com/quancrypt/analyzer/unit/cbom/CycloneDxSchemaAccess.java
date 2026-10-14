package com.quancrypt.analyzer.unit.cbom;

import com.networknt.schema.Error;
import java.util.List;

/** Public door to the CycloneDX 1.6 schema validation of this test package, for the golden test. */
public final class CycloneDxSchemaAccess {

    private CycloneDxSchemaAccess() {
    }

    public static List<Error> validate(String json) {
        return CycloneDxSchema.validate(json);
    }
}
