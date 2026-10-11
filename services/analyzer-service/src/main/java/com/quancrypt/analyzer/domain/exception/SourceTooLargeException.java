package com.quancrypt.analyzer.domain.exception;

/** A file or a project exceeds the reading limits. The message is a fixed sentence and never repeats the caller's input. */
public final class SourceTooLargeException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public SourceTooLargeException(String message) {
        super(message);
    }
}
