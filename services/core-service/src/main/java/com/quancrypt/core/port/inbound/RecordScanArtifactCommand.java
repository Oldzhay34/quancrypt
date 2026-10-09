package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Stores the CBOM file of a running scan (at most 20 MiB). */
public record RecordScanArtifactCommand(UUID scanId, String contentType, byte[] content, String caller) {

    public RecordScanArtifactCommand {
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
