package com.quancrypt.core.usecase;

import com.quancrypt.core.port.inbound.ListScansQuery;
import com.quancrypt.core.port.inbound.ListScansUseCase;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.TransactionRunner;

/** Lists the scans of a project, newest first. */
public final class ListScansService implements ListScansUseCase {

    private final TransactionRunner tx;
    private final ProjectReader projects;
    private final ScanReader scans;

    public ListScansService(TransactionRunner tx, ProjectReader projects, ScanReader scans) {
        this.tx = tx;
        this.projects = projects;
        this.scans = scans;
    }

    @Override
    public PageView<ScanView> execute(ListScansQuery input) {
        Guard.page(input.page(), input.size());
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            projects.findById(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            return ViewMapper.page(scans.pageByProject(input.projectId(), input.page(), input.size()), ViewMapper::scan);
        });
    }
}
