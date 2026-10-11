package com.quancrypt.analyzer.domain.model;

import java.util.List;
import java.util.Objects;

/** Consecutive lines of a file around a line asked for (at most 10 on each side). */
public record Snippet(RelativePath path, List<SnippetLine> lines) {

    public static final int MAX_CONTEXT = 10;
    public static final int MAX_LINES = 2 * MAX_CONTEXT + 1;

    public Snippet {
        Objects.requireNonNull(path, "path");
        lines = List.copyOf(lines);
        if (lines.size() > MAX_LINES) {
            throw new IllegalArgumentException("a snippet has at most 21 lines");
        }
    }
}
