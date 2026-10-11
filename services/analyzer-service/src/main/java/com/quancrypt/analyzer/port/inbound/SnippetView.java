package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** Redacted lines of a file. */
public record SnippetView(String path, List<SnippetLineView> lines) {

    public SnippetView {
        lines = List.copyOf(lines);
    }
}
