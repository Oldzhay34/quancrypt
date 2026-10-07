package com.quancrypt.qbank.payment.port.inbound;

/** The request is malformed. Part of the use case contract. */
public class InvalidRequestException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public InvalidRequestException(String message) {
        super(message);
    }
}
