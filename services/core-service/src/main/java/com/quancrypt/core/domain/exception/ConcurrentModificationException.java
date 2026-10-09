package com.quancrypt.core.domain.exception;

/** An optimistic lock failed: the row was changed by someone else (HTTP 409 concurrent-modification). */
public final class ConcurrentModificationException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ConcurrentModificationException(String what) {
        super(what + " was changed concurrently");
    }
}
