package com.quancrypt.core.port.outbound;

/** What the plan needs to know about a finding beyond its own fields: device link and call sites (D-124, D-148). */
public record FindingContext(boolean onDeviceLink, int callSiteCount) {
}
