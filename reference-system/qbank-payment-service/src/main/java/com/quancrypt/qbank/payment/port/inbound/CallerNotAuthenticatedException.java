package com.quancrypt.qbank.payment.port.inbound;

/** The account service did not accept the caller's token. */
public class CallerNotAuthenticatedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public CallerNotAuthenticatedException() {
        super("the caller is not authenticated");
    }
}
