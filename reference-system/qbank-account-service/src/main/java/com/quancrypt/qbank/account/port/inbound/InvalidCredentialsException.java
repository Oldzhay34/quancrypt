package com.quancrypt.qbank.account.port.inbound;

/** Unknown username or wrong password; the two cases are deliberately indistinguishable. */
public class InvalidCredentialsException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public InvalidCredentialsException() {
        super("invalid credentials");
    }
}
