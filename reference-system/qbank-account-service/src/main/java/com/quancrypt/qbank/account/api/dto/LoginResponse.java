package com.quancrypt.qbank.account.api.dto;

/** Response body of POST /api/v1/auth/login. */
public record LoginResponse(String accessToken, String tokenType, long expiresIn) {

    @Override
    public String toString() {
        return "LoginResponse[accessToken=****, tokenType=" + tokenType + ", expiresIn=" + expiresIn + "]";
    }
}
