package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Optional;

/** Path arithmetic on '/' separated paths relative to the analyzed root, never leaving it. */
final class ProjectPaths {

    private ProjectPaths() {
    }

    /** {@code relative} resolved against {@code baseDirectory} (empty for the root), normalised; empty when it is absolute or leaves the root. */
    static Optional<String> resolve(String baseDirectory, String relative) {
        String text = relative.strip();
        if (text.isEmpty() || text.startsWith("/") || text.startsWith("~") || text.startsWith("$") || text.indexOf('\\') >= 0
                || (text.length() > 1 && text.charAt(1) == ':')) {
            return Optional.empty();
        }
        Deque<String> parts = new ArrayDeque<>();
        if (!baseDirectory.isEmpty()) {
            for (String part : baseDirectory.split("/")) {
                parts.addLast(part);
            }
        }
        for (String part : text.split("/")) {
            if (part.isEmpty() || part.equals(".")) {
                continue;
            }
            if (part.equals("..")) {
                if (parts.isEmpty()) {
                    return Optional.empty();
                }
                parts.removeLast();
            } else {
                parts.addLast(part);
            }
        }
        return Optional.of(String.join("/", parts));
    }

    static String directoryOf(String path) {
        int slash = path.lastIndexOf('/');
        return slash < 0 ? "" : path.substring(0, slash);
    }

    static String baseName(String path) {
        return path.substring(path.lastIndexOf('/') + 1);
    }

    /** The node id a text can be: only the characters the contract allows, at most 200. */
    static String nodeId(String text) {
        String cleaned = text.replaceAll("[^A-Za-z0-9._-]", "-");
        cleaned = cleaned.length() > 200 ? cleaned.substring(0, 200) : cleaned;
        return cleaned.isEmpty() ? "unnamed" : cleaned;
    }
}
