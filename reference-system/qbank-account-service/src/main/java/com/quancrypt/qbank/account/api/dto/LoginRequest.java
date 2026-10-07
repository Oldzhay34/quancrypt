package com.quancrypt.qbank.account.api.dto;

/** Request body of POST /api/v1/auth/login. Unknown properties are rejected (application.yml, spring.jackson). */
public record LoginRequest(String username, String password) {

    @Override
    public String toString() {
        return "LoginRequest[username=" + username + ", password=****]";
    }
}
