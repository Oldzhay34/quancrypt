package com.quancrypt.core.domain.exception;

/** The project already has a running scan (partial unique index violated). */
public final class ScanAlreadyRunningException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ScanAlreadyRunningException() {
        super("the project already has a running scan");
    }
}
