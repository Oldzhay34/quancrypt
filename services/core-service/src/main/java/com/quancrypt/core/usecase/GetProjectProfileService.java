package com.quancrypt.core.usecase;

import com.quancrypt.core.port.inbound.GetProjectProfileQuery;
import com.quancrypt.core.port.inbound.GetProjectProfileUseCase;
import com.quancrypt.core.port.inbound.view.ProjectProfileView;
import com.quancrypt.core.port.outbound.ClarificationReader;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.TransactionRunner;

/** Reads the runtime profile and the clarification answers of a project. */
public final class GetProjectProfileService implements GetProjectProfileUseCase {

    private final TransactionRunner tx;
    private final ProjectReader projects;
    private final RuntimeProfileReader profiles;
    private final ClarificationReader answers;

    public GetProjectProfileService(TransactionRunner tx, ProjectReader projects, RuntimeProfileReader profiles, ClarificationReader answers) {
        this.tx = tx;
        this.projects = projects;
        this.profiles = profiles;
        this.answers = answers;
    }

    @Override
    public ProjectProfileView execute(GetProjectProfileQuery input) {
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            projects.findById(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            return new ProjectProfileView(
                    profiles.current(input.projectId()).map(p -> ViewMapper.runtimeProfile(p, false)),
                    answers.list(input.projectId()).stream().map(ViewMapper::answer).toList());
        });
    }
}
