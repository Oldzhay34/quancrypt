package com.quancrypt.core.port.outbound;

/** The receiver of outbox events could not be reached or refused the batch; the events stay unsent. */
public final class PublishFailedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public PublishFailedException(String detail) {
        super(detail);
    }
}
