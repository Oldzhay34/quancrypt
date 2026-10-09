package com.quancrypt.core.port.inbound;

import java.util.Optional;

/** One clarification answer. */
public record ClarificationAnswerInput(String questionCode, Optional<String> optionCode, Optional<String> freeText) {
}
