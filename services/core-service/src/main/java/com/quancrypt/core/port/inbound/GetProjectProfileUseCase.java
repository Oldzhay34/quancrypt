package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ProjectProfileView;

/** Reads the project profile. */
public interface GetProjectProfileUseCase {

    ProjectProfileView execute(GetProjectProfileQuery input);
}
