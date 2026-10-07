package com.quancrypt.qbank.account.facade.error;

/** The requested resource does not exist (maps to HTTP 404 in the api layer). */
public class ResourceNotFoundException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ResourceNotFoundException() {
        super("not found");
    }
}
