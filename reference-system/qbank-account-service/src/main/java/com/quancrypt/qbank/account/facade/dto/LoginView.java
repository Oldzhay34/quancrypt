package com.quancrypt.qbank.account.facade.dto;

/** Result of a successful login as seen by the api layer. */
public record LoginView(String accessToken, String tokenType, long expiresIn) {

    @Override
    public String toString() {
        return "LoginView[accessToken=****, tokenType=" + tokenType + ", expiresIn=" + expiresIn + "]";
    }
}
