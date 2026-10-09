package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.ProjectKey;

/** Reads audit rows. */
public interface AuditLogReader {

    PageResult<AuditEntry> page(ProjectKey projectKey, int page, int size);
}
