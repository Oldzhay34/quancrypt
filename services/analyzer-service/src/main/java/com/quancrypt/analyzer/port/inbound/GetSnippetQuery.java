package com.quancrypt.analyzer.port.inbound;

/** A line of a file and how many lines around it (0 to 10). */
public record GetSnippetQuery(String root, String path, int line, int context) {
}
