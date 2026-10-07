package com.quancrypt.qbank.payment.facade.error;

/** The request is malformed (maps to HTTP 400 in the api layer). */
public class BadRequestException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public BadRequestException(String message) {
        super(message);
    }
}
