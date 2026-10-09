package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.ScanArtifact;
import java.util.Optional;
import java.util.UUID;

/** Reads CBOM files. */
public interface ScanArtifactReader {

    Optional<ScanArtifact> find(UUID scanId);
}
