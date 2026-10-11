package com.quancrypt.core.facade.dto;

import java.util.List;

/** The saved clarification answers (response of SaveClarificationAnswers; schema ClarificationAnswerSet). */
public record ClarificationAnswerSetDto(List<ClarificationAnswerDto> answers) {

    public ClarificationAnswerSetDto {
        answers = answers == null ? null : List.copyOf(answers);
    }
}

