package com.quancrypt.qbank.payment.port.inbound;

/** The idempotency key was already used with a different request. */
public class IdempotencyConflictException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public IdempotencyConflictException() {
        super("idempotency key reused with a different request");
    }
}
