package com.quancrypt.analyzer.facade.dto;

import java.util.List;

/** Redacted, numbered lines of a file (contract `Snippet`). */
public record SnippetDto(String path, List<LineDto> lines) {

    public SnippetDto {
        lines = List.copyOf(lines);
    }

    /** One line. */
    public record LineDto(int number, String text) {
    }
}
