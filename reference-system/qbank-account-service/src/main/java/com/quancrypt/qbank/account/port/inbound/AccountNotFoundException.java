package com.quancrypt.qbank.account.port.inbound;

/** The requested account does not exist. */
public class AccountNotFoundException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public AccountNotFoundException() {
        super("account not found");
    }
}
