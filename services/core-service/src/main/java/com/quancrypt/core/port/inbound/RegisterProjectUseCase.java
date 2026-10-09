package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ProjectView;

/** Registers a project (idempotent by project key). */
public interface RegisterProjectUseCase {

    ProjectView execute(RegisterProjectCommand input);
}
