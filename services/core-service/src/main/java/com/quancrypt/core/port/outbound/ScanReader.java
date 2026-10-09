package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Scan;
import java.util.Optional;
import java.util.UUID;

/** Reads scans. */
public interface ScanReader {

    Optional<Scan> find(UUID scanId);

    /** Plain read of the owning project, so the project lock can be taken first (D-143). */
    Optional<UUID> projectIdOf(UUID scanId);

    PageResult<Scan> pageByProject(UUID projectId, int page, int size);
}
