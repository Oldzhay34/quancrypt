package com.quancrypt.analyzer.domain.exception;

/** A root or path leaves the allowed directories, the root, or passes through a symbolic link. The message is a fixed sentence and never repeats the caller's input. */
public final class PathNotAllowedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public PathNotAllowedException(String message) {
        super(message);
    }
}
