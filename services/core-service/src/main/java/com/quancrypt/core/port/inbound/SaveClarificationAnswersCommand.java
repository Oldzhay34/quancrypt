package com.quancrypt.core.port.inbound;

import java.util.List;
import java.util.UUID;

/** Saves up to five clarification answers. */
public record SaveClarificationAnswersCommand(UUID projectId, List<ClarificationAnswerInput> answers, String caller) {

    public SaveClarificationAnswersCommand {
        answers = List.copyOf(answers);
    }
}
