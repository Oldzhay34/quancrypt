package com.quancrypt.core.domain.model;

import java.util.UUID;

/** Where in a source file a link is called. */
public record CallSite(UUID sourceFileId, int lineStart, int lineEnd) {

    public CallSite {
        if (lineStart < 1 || lineEnd < lineStart) {
            throw new IllegalArgumentException("line range must start at 1 or later and not end before it starts");
        }
    }
}
