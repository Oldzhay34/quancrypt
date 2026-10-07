package com.quancrypt.qbank.payment.facade.error;

/** The request conflicts with an earlier one (maps to HTTP 409 in the api layer). */
public class ConflictException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ConflictException() {
        super("conflict");
    }
}
