package com.quancrypt.analyzer.facade.dto;

/** The body of AnalyzeCrypto: `root` is required, `include_tests` defaults to true (D-173). */
public record AnalysisRequestInput(String root, Boolean includeTests) {
}
