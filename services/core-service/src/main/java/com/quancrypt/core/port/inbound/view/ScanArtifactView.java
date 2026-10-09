package com.quancrypt.core.port.inbound.view;

import java.time.Instant;
import java.util.UUID;

/** Metadata of a scan's CBOM file. */
public record ScanArtifactView(UUID scanId, String contentType, String sha256, Instant createdAt) {
}
