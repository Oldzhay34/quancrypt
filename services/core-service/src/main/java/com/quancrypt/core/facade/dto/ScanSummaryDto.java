package com.quancrypt.core.facade.dto;

import java.util.Map;

/** Scan summary (schema ScanSummary). */
public record ScanSummaryDto(ScanDto scan, RuntimeProfileDto runtimeProfile, int findingCount, Map<String, Integer> countsByPriority, Map<String, Integer> countsByAlgorithmFamily, Map<String, Integer> countsByLocationKind) {

    public ScanSummaryDto {
        countsByPriority = countsByPriority == null ? null : Map.copyOf(countsByPriority);
        countsByAlgorithmFamily = countsByAlgorithmFamily == null ? null : Map.copyOf(countsByAlgorithmFamily);
        countsByLocationKind = countsByLocationKind == null ? null : Map.copyOf(countsByLocationKind);
    }
}

