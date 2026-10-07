package com.quancrypt.qbank.account.port.inbound;

/** The requester does not own the requested account. */
public class AccountAccessDeniedException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public AccountAccessDeniedException() {
        super("access to the account is denied");
    }
}
