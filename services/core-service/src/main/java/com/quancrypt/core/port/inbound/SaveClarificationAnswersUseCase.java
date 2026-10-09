package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ProjectProfileView;

/** Saves clarification answers. */
public interface SaveClarificationAnswersUseCase {

    ProjectProfileView execute(SaveClarificationAnswersCommand input);
}
