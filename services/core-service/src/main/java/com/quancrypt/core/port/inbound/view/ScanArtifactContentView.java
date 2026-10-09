package com.quancrypt.core.port.inbound.view;

/** A scan's CBOM file with its metadata. */
public record ScanArtifactContentView(String contentType, String sha256, byte[] content) {

    public ScanArtifactContentView {
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
