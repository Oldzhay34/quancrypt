package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.UUID;

/** A software project Quancrypt scans; identified only by its HMAC project key (D-129). */
public record Project(UUID id, ProjectKey key, String displayName, Instant createdAt) {

    public static final int MAX_DISPLAY_NAME = 200;

    public Project {
        if (displayName == null || displayName.isBlank() || displayName.length() > MAX_DISPLAY_NAME) {
            throw new IllegalArgumentException("display name must be 1.." + MAX_DISPLAY_NAME + " characters");
        }
    }
}
