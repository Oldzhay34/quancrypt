package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.ProjectView;

/** Lists projects. */
public interface ListProjectsUseCase {

    PageView<ProjectView> execute(ListProjectsQuery input);
}
