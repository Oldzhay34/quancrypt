package com.quancrypt.core.port.inbound.view;

/** A call site of a link. */
public record CallSiteView(String path, int lineStart, int lineEnd, String locationKind) {
}
