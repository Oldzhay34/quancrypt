package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.AuditEntryView;
import com.quancrypt.core.port.inbound.view.PageView;

/** Lists audit rows of a project key. */
public interface GetAuditLogUseCase {

    PageView<AuditEntryView> execute(GetAuditLogQuery input);
}
