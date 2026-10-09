package com.quancrypt.core.port.inbound;

/** One call site of a link. */
public record CallSiteInput(String path, int lineStart, int lineEnd, String locationKind) {
}
