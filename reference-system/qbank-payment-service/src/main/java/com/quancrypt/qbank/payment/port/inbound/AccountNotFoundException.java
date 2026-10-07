package com.quancrypt.qbank.payment.port.inbound;

/** The account of a payment does not exist. */
public class AccountNotFoundException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public AccountNotFoundException() {
        super("account not found");
    }
}
