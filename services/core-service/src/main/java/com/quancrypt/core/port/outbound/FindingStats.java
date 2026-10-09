package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import java.util.Map;

/** Finding counts of a scan, grouped in one query. */
public record FindingStats(
        int total,
        Map<Priority, Integer> byPriority,
        Map<AlgorithmFamily, Integer> byAlgorithmFamily,
        Map<LocationKind, Integer> byLocationKind) {

    public FindingStats {
        byPriority = Map.copyOf(byPriority);
        byAlgorithmFamily = Map.copyOf(byAlgorithmFamily);
        byLocationKind = Map.copyOf(byLocationKind);
    }
}
