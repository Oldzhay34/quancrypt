package com.quancrypt.analyzer.domain.model;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import java.util.List;
import java.util.Objects;

/**
 * A path relative to the analysis root, '/' separated. Absolute paths, drive letters, backslashes, control characters
 * and empty, "." or ".." segments are refused, so the path can never name anything outside the root by itself.
 */
public record RelativePath(String value) {

    public static final int MAX_LENGTH = 1024;

    public RelativePath {
        Objects.requireNonNull(value, "value");
        if (value.isEmpty() || value.length() > MAX_LENGTH) {
            throw new PathNotAllowedException("the path must be 1 to 1024 characters");
        }
        if (value.startsWith("/") || value.indexOf('\\') >= 0 || hasDriveLetter(value)) {
            throw new PathNotAllowedException("the path must be relative and '/' separated");
        }
        if (Text.hasControl(value)) {
            throw new PathNotAllowedException("the path contains a control character");
        }
        for (String segment : value.split("/", -1)) {
            if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) {
                throw new PathNotAllowedException("the path has an empty, '.' or '..' segment");
            }
        }
    }

    public static RelativePath of(String value) {
        return new RelativePath(value);
    }

    public List<String> segments() {
        return List.of(value.split("/"));
    }

    private static boolean hasDriveLetter(String value) {
        return value.length() >= 2 && value.charAt(1) == ':' && Character.isLetter(value.charAt(0));
    }
}
