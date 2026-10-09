package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.inbound.GetProjectQuery;
import com.quancrypt.core.port.inbound.GetProjectUseCase;
import com.quancrypt.core.port.inbound.view.ProjectDetailView;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.TransactionRunner;

/** Reads a project with its current runtime profile. */
public final class GetProjectService implements GetProjectUseCase {

    private final TransactionRunner tx;
    private final ProjectReader projects;
    private final RuntimeProfileReader profiles;

    public GetProjectService(TransactionRunner tx, ProjectReader projects, RuntimeProfileReader profiles) {
        this.tx = tx;
        this.projects = projects;
        this.profiles = profiles;
    }

    @Override
    public ProjectDetailView execute(GetProjectQuery input) {
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Project project = projects.findById(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            return new ProjectDetailView(
                    ViewMapper.project(project, false),
                    profiles.current(project.id()).map(p -> ViewMapper.runtimeProfile(p, false)));
        });
    }
}
