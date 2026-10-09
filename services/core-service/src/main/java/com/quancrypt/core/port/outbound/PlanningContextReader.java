package com.quancrypt.core.port.outbound;

import java.util.Map;
import java.util.UUID;

/** Reads topology-derived facts of findings. */
public interface PlanningContextReader {

    /** The context of every finding of the scan, keyed by finding id. */
    Map<UUID, FindingContext> load(UUID scanId);
}
