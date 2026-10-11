package com.quancrypt.analyzer.domain.exception;

/** The project cannot be analyzed: unknown build system, two build systems or no plugin. The message is a fixed sentence and never repeats the caller's input. */
public final class UnsupportedProjectException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public UnsupportedProjectException(String message) {
        super(message);
    }
}
