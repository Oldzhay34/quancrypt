package com.quancrypt.core.port.inbound.view;

import java.util.Map;
import java.util.Optional;

/** A scan with finding counts. */
public record ScanSummaryView(ScanView scan, Optional<RuntimeProfileView> runtimeProfile, int findingCount, Map<String, Integer> countsByPriority, Map<String, Integer> countsByAlgorithmFamily, Map<String, Integer> countsByLocationKind) {

    public ScanSummaryView {
        countsByPriority = Map.copyOf(countsByPriority);
        countsByAlgorithmFamily = Map.copyOf(countsByAlgorithmFamily);
        countsByLocationKind = Map.copyOf(countsByLocationKind);
    }
}
