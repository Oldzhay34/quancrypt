package com.quancrypt.core.port.inbound.view;

import java.util.List;
import java.util.Optional;

/** Runtime profile and clarification answers of a project. */
public record ProjectProfileView(Optional<RuntimeProfileView> runtimeProfile, List<ClarificationAnswerView> answers) {

    public ProjectProfileView {
        answers = List.copyOf(answers);
    }
}
