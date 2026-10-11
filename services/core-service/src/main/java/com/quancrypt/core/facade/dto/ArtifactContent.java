package com.quancrypt.core.facade.dto;

/** CBOM file content with its type and digest (for the ETag header). */
public record ArtifactContent(String contentType, String sha256, byte[] content) {

    public ArtifactContent {
        content = content == null ? null : content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}

