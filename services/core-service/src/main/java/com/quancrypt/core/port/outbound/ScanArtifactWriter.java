package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.ScanArtifact;

/** Writes CBOM files. */
public interface ScanArtifactWriter {

    /** Stores the file, replacing the scan's previous one. */
    void save(ScanArtifact artifact);
}
