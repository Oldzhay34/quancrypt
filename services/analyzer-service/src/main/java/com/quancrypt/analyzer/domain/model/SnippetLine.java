package com.quancrypt.analyzer.domain.model;

import java.util.Objects;

/** One numbered line of a snippet. */
public record SnippetLine(int number, String text) {

    public SnippetLine {
        if (number < 1) {
            throw new IllegalArgumentException("line numbers start at 1");
        }
        Objects.requireNonNull(text, "text");
    }
}
