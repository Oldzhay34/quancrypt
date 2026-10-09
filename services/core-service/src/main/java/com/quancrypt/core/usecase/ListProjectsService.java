package com.quancrypt.core.usecase;

import com.quancrypt.core.port.inbound.ListProjectsQuery;
import com.quancrypt.core.port.inbound.ListProjectsUseCase;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.ProjectView;
import com.quancrypt.core.port.outbound.ProjectReader;

/** Lists projects, newest first. */
public final class ListProjectsService implements ListProjectsUseCase {

    private final ProjectReader projects;

    public ListProjectsService(ProjectReader projects) {
        this.projects = projects;
    }

    @Override
    public PageView<ProjectView> execute(ListProjectsQuery input) {
        Guard.page(input.page(), input.size());
        return ViewMapper.page(projects.page(input.page(), input.size()), p -> ViewMapper.project(p, false));
    }
}
