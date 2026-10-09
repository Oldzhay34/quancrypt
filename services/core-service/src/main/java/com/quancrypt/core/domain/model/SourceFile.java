package com.quancrypt.core.domain.model;

import java.util.UUID;

/** A source file seen in a scan; the path is relative to the project root. The kind is a property of the file (D-140). */
public record SourceFile(UUID id, UUID scanId, String path, LocationKind locationKind) {

    public static final int MAX_PATH = 1024;

    public SourceFile {
        if (path == null || path.isBlank() || path.length() > MAX_PATH) {
            throw new IllegalArgumentException("path must be 1.." + MAX_PATH + " characters");
        }
    }
}
