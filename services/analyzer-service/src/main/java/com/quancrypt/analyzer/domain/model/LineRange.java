package com.quancrypt.analyzer.domain.model;

/** A 1-based, inclusive line range. */
public record LineRange(int start, int end) {

    public LineRange {
        if (start < 1 || end < start) {
            throw new IllegalArgumentException("a line range starts at 1 and does not end before it starts");
        }
    }
}
