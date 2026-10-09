package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads a scan's CBOM file. */
public record GetScanArtifactQuery(UUID scanId) {
}
