package com.quancrypt.analyzer.domain.model;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import java.util.Objects;

/**
 * An absolute, canonical directory path the analysis starts from: '/' separated, no trailing slash, no empty, "." or
 * ".." segment, no backslash or control character. Whether it lies under an allowed directory is decided by
 * {@link AllowedRoots}; symbolic links are refused by the source tree reader.
 */
public record AnalysisRoot(String value) {

    public static final int MAX_LENGTH = 1024;

    public AnalysisRoot {
        Objects.requireNonNull(value, "value");
        if (!isCanonicalAbsolute(value)) {
            throw new PathNotAllowedException("the root must be a canonical absolute path");
        }
    }

    /** Whether the root is the given directory or lies below it. */
    boolean isAtOrBelow(String directory) {
        return value.equals(directory) || value.startsWith(directory + "/");
    }

    static boolean isCanonicalAbsolute(String value) {
        if (value.length() < 2 || value.length() > MAX_LENGTH || value.charAt(0) != '/' || value.indexOf('\\') >= 0
                || Text.hasControl(value)) {
            return false;
        }
        for (String segment : value.substring(1).split("/", -1)) {
            if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) {
                return false;
            }
        }
        return true;
    }
}
