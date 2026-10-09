package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanStatus;
import java.time.Instant;
import java.util.UUID;

/** Writes scans. */
public interface ScanWriter {

    /** Throws ScanAlreadyRunningException when the project already has a running scan. */
    void insertRunning(Scan scan);

    /** Conditional update; false when the scan was no longer running. */
    boolean finishIfRunning(UUID scanId, ScanStatus outcome, Instant at);
}
