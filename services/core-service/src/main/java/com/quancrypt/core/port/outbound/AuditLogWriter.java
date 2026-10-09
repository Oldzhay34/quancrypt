package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.AuditEntry;

/** Appends audit rows. */
public interface AuditLogWriter {

    void append(AuditEntry entry);
}
