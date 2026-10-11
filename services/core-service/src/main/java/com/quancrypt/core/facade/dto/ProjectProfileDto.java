package com.quancrypt.core.facade.dto;

import java.util.List;

/** Project profile (schema ProjectProfile). */
public record ProjectProfileDto(RuntimeProfileDto runtimeProfile, List<ClarificationAnswerDto> answers) {

    public ProjectProfileDto {
        answers = answers == null ? null : List.copyOf(answers);
    }
}

