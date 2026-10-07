package com.quancrypt.qbank.payment.facade.error;

/** The caller could not be authenticated (maps to HTTP 401 in the api layer). */
public class UnauthorizedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public UnauthorizedException() {
        super("unauthorized");
    }
}
