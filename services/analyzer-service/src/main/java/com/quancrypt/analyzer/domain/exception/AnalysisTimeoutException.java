package com.quancrypt.analyzer.domain.exception;

/** The analysis ran past its time budget (D-199). The message is a fixed sentence and never repeats the caller's input. */
public final class AnalysisTimeoutException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public AnalysisTimeoutException(String message) {
        super(message);
    }
}
