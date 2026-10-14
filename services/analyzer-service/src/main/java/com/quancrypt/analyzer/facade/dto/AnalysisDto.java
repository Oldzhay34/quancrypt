package com.quancrypt.analyzer.facade.dto;

import java.util.List;
import java.util.UUID;

/**
 * The result of one analysis as the contract names it (`AnalysisResult`). Field names become snake_case on the wire
 * (D-175). The CBOM travels as a JSON document string; the api layer writes it as the JSON object it is.
 */
public record AnalysisDto(UUID analysisId, String projectType, RuntimeDto runtime, List<FindingDto> findings, String cbom,
        StatsDto stats) {

    public AnalysisDto {
        findings = List.copyOf(findings);
    }

    /** Build-file versions; absent ones are null. */
    public record RuntimeDto(String javaVersion, String springBootVersion) {
    }

    /** One finding as finding.schema.json describes it. */
    public record FindingDto(String file, Integer lineStart, Integer lineEnd, String rawName, String symbol, String algorithmFamily,
            String mode, String padding, String hash, Integer keySizeBits, String usageContext, String locationKind, String priority,
            String library, double confidence, String detectorId) {
    }

    /** Counters of one analysis. */
    public record StatsDto(int filesScanned, int findingsTotal, long durationMs) {
    }
}
