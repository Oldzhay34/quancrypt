package com.quancrypt.analyzer.domain.model;

import java.util.Objects;
import java.util.regex.Pattern;

/** A CycloneDX BOM as a JSON document and its specification version (1.6, D-195). */
public record Cbom(String specVersion, String json) {

    private static final Pattern SPEC_VERSION = Pattern.compile("[0-9]+\\.[0-9]+");

    public Cbom {
        Text.matching(specVersion, SPEC_VERSION, "specVersion");
        Objects.requireNonNull(json, "json");
    }
}
