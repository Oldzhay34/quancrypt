package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.AuditEntryDto;
import com.quancrypt.core.facade.dto.PageDto;
import com.quancrypt.core.port.inbound.GetAuditLogQuery;
import com.quancrypt.core.port.inbound.GetAuditLogUseCase;

/** The audit log of a project (read only). */
public final class AuditFacade {

    private final GetAuditLogUseCase getAuditLog;

    public AuditFacade(GetAuditLogUseCase getAuditLog) {
        this.getAuditLog = getAuditLog;
    }

    public PageDto<AuditEntryDto> entries(String projectKey, int page, int size) {
        return ProblemTranslator.call(() -> FacadeMapper.page(getAuditLog.execute(new GetAuditLogQuery(projectKey, page, size)), FacadeMapper::audit));
    }
}
