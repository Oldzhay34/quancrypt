package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.inbound.GetAuditLogQuery;
import com.quancrypt.core.port.inbound.GetAuditLogUseCase;
import com.quancrypt.core.port.inbound.view.AuditEntryView;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.outbound.AuditLogReader;

/** Lists the audit rows of a project key, newest first. */
public final class GetAuditLogService implements GetAuditLogUseCase {

    private final AuditLogReader audit;

    public GetAuditLogService(AuditLogReader audit) {
        this.audit = audit;
    }

    @Override
    public PageView<AuditEntryView> execute(GetAuditLogQuery input) {
        Guard.page(input.page(), input.size());
        ProjectKey key = Guard.valid(() -> new ProjectKey(input.projectKey()));
        return ViewMapper.page(audit.page(key, input.page(), input.size()), ViewMapper::audit);
    }
}
