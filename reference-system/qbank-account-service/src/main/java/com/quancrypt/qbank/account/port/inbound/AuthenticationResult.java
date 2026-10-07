package com.quancrypt.qbank.account.port.inbound;

/** An issued access token and its lifetime in seconds. */
public record AuthenticationResult(String accessToken, long expiresInSeconds) {

    @Override
    public String toString() {
        return "AuthenticationResult[accessToken=****, expiresInSeconds=" + expiresInSeconds + "]";
    }
}
