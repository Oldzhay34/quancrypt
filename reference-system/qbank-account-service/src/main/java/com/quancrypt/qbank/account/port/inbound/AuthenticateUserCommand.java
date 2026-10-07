package com.quancrypt.qbank.account.port.inbound;

/** Login request of a user. */
public record AuthenticateUserCommand(String username, String password) {

    @Override
    public String toString() {
        return "AuthenticateUserCommand[username=" + username + ", password=****]";
    }
}
