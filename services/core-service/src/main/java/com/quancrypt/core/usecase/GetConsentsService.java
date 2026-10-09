package com.quancrypt.core.usecase;

import com.quancrypt.core.port.inbound.GetConsentsQuery;
import com.quancrypt.core.port.inbound.GetConsentsUseCase;
import com.quancrypt.core.port.inbound.view.ConsentListView;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.TransactionRunner;

/** Lists the consents of a project. */
public final class GetConsentsService implements GetConsentsUseCase {

    private final TransactionRunner tx;
    private final ProjectReader projects;
    private final ConsentReader consents;

    public GetConsentsService(TransactionRunner tx, ProjectReader projects, ConsentReader consents) {
        this.tx = tx;
        this.projects = projects;
        this.consents = consents;
    }

    @Override
    public ConsentListView execute(GetConsentsQuery input) {
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            projects.findById(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            return new ConsentListView(consents.list(input.projectId()).stream().map(c -> ViewMapper.consent(c, false)).toList());
        });
    }
}
