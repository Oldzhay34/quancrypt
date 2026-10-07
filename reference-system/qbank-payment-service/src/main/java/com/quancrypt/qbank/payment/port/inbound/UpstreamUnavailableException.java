package com.quancrypt.qbank.payment.port.inbound;

/** The account service is unreachable or its circuit breaker is open. */
public class UpstreamUnavailableException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public UpstreamUnavailableException() {
        super("the account service is unavailable");
    }
}
