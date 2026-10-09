package com.quancrypt.core.port.inbound;

/** Lists the audit rows of a project key. */
public record GetAuditLogQuery(String projectKey, int page, int size) {
}
