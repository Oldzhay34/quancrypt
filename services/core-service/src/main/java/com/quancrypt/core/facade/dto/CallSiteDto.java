package com.quancrypt.core.facade.dto;

/** Call site (schema CallSiteInput). */
public record CallSiteDto(String path, int lineStart, int lineEnd, String locationKind) {
}
