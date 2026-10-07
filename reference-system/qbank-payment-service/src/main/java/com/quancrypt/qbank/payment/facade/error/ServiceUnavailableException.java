package com.quancrypt.qbank.payment.facade.error;

/** A required upstream service is unavailable (maps to HTTP 503 in the api layer). */
public class ServiceUnavailableException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ServiceUnavailableException() {
        super("service unavailable");
    }
}
