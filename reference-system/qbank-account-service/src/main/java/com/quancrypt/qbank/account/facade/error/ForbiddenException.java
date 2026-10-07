package com.quancrypt.qbank.account.facade.error;

/** The caller is authenticated but not allowed (maps to HTTP 403 in the api layer). */
public class ForbiddenException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ForbiddenException() {
        super("forbidden");
    }
}
