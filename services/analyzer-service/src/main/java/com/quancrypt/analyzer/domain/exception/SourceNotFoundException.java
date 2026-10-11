package com.quancrypt.analyzer.domain.exception;

/** A file or a line that was asked for does not exist. The message is a fixed sentence and never repeats the caller's input. */
public final class SourceNotFoundException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public SourceNotFoundException(String message) {
        super(message);
    }
}
