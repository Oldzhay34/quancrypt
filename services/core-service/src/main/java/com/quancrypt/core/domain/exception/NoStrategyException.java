package com.quancrypt.core.domain.exception;

/** No migration strategy (or more than one) supports a finding; a configuration or data error. */
public final class NoStrategyException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public NoStrategyException(String detail) {
        super(detail);
    }
}
