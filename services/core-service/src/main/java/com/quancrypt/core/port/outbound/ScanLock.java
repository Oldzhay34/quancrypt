package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Scan;
import java.util.Optional;
import java.util.UUID;

/** Row locks on a scan. */
public interface ScanLock {

    Optional<Scan> noKeyUpdate(UUID scanId);

    Optional<Scan> share(UUID scanId);
}
