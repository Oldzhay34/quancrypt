package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ProjectDetailView;

/** Reads a project and its current runtime profile. */
public interface GetProjectUseCase {

    ProjectDetailView execute(GetProjectQuery input);
}
