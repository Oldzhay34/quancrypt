package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Optional;

/** A project's answer to one clarification question. */
public record ClarificationAnswer(ClarificationQuestion question, Optional<String> option, Optional<String> freeText, Instant answeredAt) {

    public ClarificationAnswer {
        question.validate(option, freeText);
    }
}
