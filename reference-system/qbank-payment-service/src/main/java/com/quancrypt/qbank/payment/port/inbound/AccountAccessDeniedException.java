package com.quancrypt.qbank.payment.port.inbound;

/** The account does not belong to the caller. */
public class AccountAccessDeniedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public AccountAccessDeniedException() {
        super("access to the account is denied");
    }
}
