package com.quancrypt.analyzer.port.inbound;

/** Which project to analyze and whether test code findings stay in the result (D-173). */
public record AnalyzeCryptoCommand(String root, boolean includeTests) {
}
