package com.quancrypt.core.port.inbound.view;

import java.util.Optional;

/** An answer to a clarification question. */
public record ClarificationAnswerView(String questionCode, Optional<String> optionCode, Optional<String> freeText) {
}
