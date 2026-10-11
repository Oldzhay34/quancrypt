package com.quancrypt.core.facade.dto;

import java.time.Instant;
import java.util.UUID;

/** CBOM file metadata (schema ScanArtifact). */
public record ScanArtifactDto(UUID scanId, String contentType, String sha256, Instant createdAt) {
}
