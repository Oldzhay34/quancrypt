package com.quancrypt.core.domain.model;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.UUID;

/** The CBOM file of a scan; opaque bytes with the SHA-256 the application computed when writing (D-139q). */
public record ScanArtifact(UUID scanId, String contentType, byte[] content, String sha256, Instant createdAt) {

    public static final int MAX_BYTES = 20 * 1024 * 1024;

    public ScanArtifact {
        if (content.length > MAX_BYTES) {
            throw new IllegalArgumentException("artifact is larger than 20 MiB");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException("content type is required");
        }
        content = content.clone();
    }

    public static ScanArtifact of(UUID scanId, String contentType, byte[] content, Instant at) {
        return new ScanArtifact(scanId, contentType, content, sha256Hex(content), at);
    }

    @Override
    public byte[] content() {
        return content.clone();
    }

    public static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is mandatory in every JDK", e);
        }
    }
}
