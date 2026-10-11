package com.quancrypt.core.facade.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** Body of SaveClarificationAnswers (schema ClarificationAnswerSet). */
public record ClarificationAnswerSetInput(@NotNull @Size(max = 5) List<@NotNull @Valid ClarificationAnswerDto> answers) {

    public ClarificationAnswerSetInput {
        answers = answers == null ? null : List.copyOf(answers);
    }
}

