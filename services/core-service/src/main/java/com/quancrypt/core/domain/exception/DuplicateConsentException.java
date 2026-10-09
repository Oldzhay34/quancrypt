package com.quancrypt.core.domain.exception;

/** A first consent for the same project and type was written concurrently (mapped to concurrent-modification, D-139f). */
public final class DuplicateConsentException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public DuplicateConsentException() {
        super("consent already exists for this project and type");
    }
}
